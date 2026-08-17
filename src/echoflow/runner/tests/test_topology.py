import subprocess

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.runner.models import RunnerResources
from echoflow.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    HardwareTopology,
    MemoryTopology,
    NvidiaSmiAcceleratorProbe,
    _parse_nvidia_smi,
)

MIB = 1024**2


def resources() -> RunnerResources:
    return RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=12 * 1024**3,
        memory_limit_bytes=None,
        effective_memory_available_bytes=12 * 1024**3,
    )


def cuda_device(*, index=0, total=4096 * MIB, available=3072 * MIB):
    return AcceleratorDevice(
        accelerator_id=f"cuda:{index}",
        backend=AcceleratorBackend.CUDA,
        device_index=index,
        name="Test GPU",
        memory_topology=MemoryTopology.DEDICATED,
        memory_total_bytes=total,
        memory_available_bytes=available,
    )


def test_nvidia_probe_uses_fixed_query_and_parses_multiple_devices():
    calls = []

    def run(arguments, timeout):
        calls.append((arguments, timeout))
        return "0, RTX Laptop GPU, 4096, 3072\n1, RTX Second GPU, 8192, 4096\n"

    probe = NvidiaSmiAcceleratorProbe(
        executable_resolver=lambda name: (
            "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None
        ),
        command_runner=run,
        timeout_seconds=1.5,
    )

    devices = probe.inspect()

    assert calls == [
        (
            [
                "/usr/bin/nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            1.5,
        )
    ]
    assert tuple(device.accelerator_id for device in devices) == ("cuda:0", "cuda:1")
    assert devices[0].memory_total_bytes == 4096 * MIB
    assert devices[0].memory_available_bytes == 3072 * MIB
    assert devices[0].memory_topology is MemoryTopology.DEDICATED


def test_missing_nvidia_smi_is_a_normal_cpu_only_machine():
    called = False

    def runner(_arguments, _timeout):
        nonlocal called
        called = True
        return ""

    probe = NvidiaSmiAcceleratorProbe(
        executable_resolver=lambda _name: None,
        command_runner=runner,
    )

    assert probe.inspect() == ()
    assert called is False


@pytest.mark.parametrize(
    "failure",
    [
        OSError("driver unavailable"),
        subprocess.TimeoutExpired("nvidia-smi", timeout=2),
        subprocess.CalledProcessError(1, "nvidia-smi"),
    ],
)
def test_probe_failures_degrade_to_no_accelerator_without_crashing(failure):
    def fail(_arguments, _timeout):
        raise failure

    probe = NvidiaSmiAcceleratorProbe(
        executable_resolver=lambda _name: "/usr/bin/nvidia-smi",
        command_runner=fail,
    )

    assert probe.inspect() == ()


@pytest.mark.parametrize(
    "line",
    [
        "",
        "not,enough,columns",
        "x,GPU,4096,2048",
        "-1,GPU,4096,2048",
        "0,,4096,2048",
        "0,GPU,0,0",
        "0,GPU,4096,-1",
        "0,GPU,4096,4097",
        "0,GPU,N/A,N/A",
    ],
)
def test_malformed_or_impossible_nvidia_rows_are_ignored(line):
    assert _parse_nvidia_smi(line) == ()


def test_duplicate_device_index_is_ignored_after_first_valid_row():
    devices = _parse_nvidia_smi("0,First,4096,3072\n0,Second,8192,8192\n")
    assert len(devices) == 1
    assert devices[0].name == "First"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"accelerator_id": ""}, "accelerator_id cannot be empty"),
        ({"device_index": -1}, "device_index cannot be negative"),
        ({"name": ""}, "accelerator name cannot be empty"),
        ({"memory_total_bytes": 0}, "accelerator total memory must be positive"),
        (
            {"memory_available_bytes": -1},
            "accelerator available memory cannot be negative",
        ),
        (
            {"memory_total_bytes": 10, "memory_available_bytes": 11},
            "accelerator available memory cannot exceed total memory",
        ),
    ],
)
def test_accelerator_device_rejects_invalid_boundaries(kwargs, message):
    values = {
        "accelerator_id": "cuda:0",
        "backend": AcceleratorBackend.CUDA,
        "device_index": 0,
        "name": "GPU",
        "memory_topology": MemoryTopology.DEDICATED,
        "memory_total_bytes": 10,
        "memory_available_bytes": 5,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=f"^{message}$"):
        AcceleratorDevice(**values)


def test_unknown_memory_is_representable_without_inventing_capacity():
    device = AcceleratorDevice(
        accelerator_id="future:0",
        backend=AcceleratorBackend.UNKNOWN,
        device_index=0,
        name="Future accelerator",
        memory_topology=MemoryTopology.UNKNOWN,
        memory_total_bytes=None,
        memory_available_bytes=None,
    )
    assert device.to_dict()["memory_available_bytes"] is None


def test_topology_rejects_duplicate_backend_index_and_finds_exact_device():
    device = cuda_device()
    with pytest.raises(
        ValueError, match="^accelerator backend/index pairs must be unique$"
    ):
        HardwareTopology(resources(), (device, device))

    topology = HardwareTopology(resources(), (device,))
    assert topology.find(AcceleratorBackend.CUDA, 0) is device
    assert topology.find(AcceleratorBackend.CUDA, 1) is None
    assert topology.to_dict()["accelerators"] == [device.to_dict()]


def test_probe_timeout_must_be_positive():
    with pytest.raises(
        ValueError, match="^accelerator probe timeout must be positive$"
    ):
        NvidiaSmiAcceleratorProbe(timeout_seconds=0)


@given(
    total_mib=st.integers(min_value=1, max_value=131_072),
    free_fraction=st.floats(min_value=0, max_value=1, allow_nan=False),
)
def test_property_parser_never_invents_more_free_memory_than_total(
    total_mib, free_fraction
):
    free_mib = int(total_mib * free_fraction)
    device = _parse_nvidia_smi(f"0,GPU,{total_mib},{free_mib}")[0]
    assert device.memory_total_bytes == total_mib * MIB
    assert device.memory_available_bytes == free_mib * MIB
    assert device.memory_available_bytes <= device.memory_total_bytes
