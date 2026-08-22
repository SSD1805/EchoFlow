from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scholion.runner.models import RunnerResources
from scholion.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    HardwareTopology,
    MemoryTopology,
)
from scholion.transcription.capabilities import (
    EngineCapabilities,
    EngineCapabilityRegistry,
    EngineExecutionTarget,
    FasterWhisperCapabilityProbe,
)

GIB = 1024**3


def topology(*accelerators) -> HardwareTopology:
    resources = RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=16 * GIB,
        memory_available_bytes=12 * GIB,
        memory_limit_bytes=None,
        effective_memory_available_bytes=12 * GIB,
    )
    return HardwareTopology(resources, tuple(accelerators))


def cuda(index=0) -> AcceleratorDevice:
    return AcceleratorDevice(
        accelerator_id=f"cuda:{index}",
        backend=AcceleratorBackend.CUDA,
        device_index=index,
        name="CUDA GPU",
        memory_topology=MemoryTopology.DEDICATED,
        memory_total_bytes=8 * GIB,
        memory_available_bytes=6 * GIB,
    )


def test_cpu_contract_remains_available_when_optional_runtime_is_absent():
    probe = FasterWhisperCapabilityProbe(
        module_loader=lambda _name: (_ for _ in ()).throw(ModuleNotFoundError())
    )

    capabilities = probe.inspect(topology())

    assert capabilities.engine == "faster-whisper"
    assert capabilities.targets == (
        EngineExecutionTarget(
            device="cpu",
            device_index=0,
            compute_types=("int8",),
            verified=False,
        ),
    )
    assert capabilities.supports(device="cpu", device_index=0, compute_type="int8")


def test_cuda_target_requires_both_runtime_support_and_matching_topology():
    module = SimpleNamespace(
        get_cuda_device_count=lambda: 1,
        get_supported_compute_types=lambda device, index: (
            {
                "float16",
                "int8_float16",
            }
            if (device, index) == ("cuda", 0)
            else set()
        ),
    )
    probe = FasterWhisperCapabilityProbe(module_loader=lambda _name: module)

    with_gpu = probe.inspect(topology(cuda()))
    without_gpu = probe.inspect(topology())

    assert with_gpu.supports(device="cuda", device_index=0, compute_type="float16")
    assert with_gpu.supports(device="cuda", device_index=0, compute_type="int8_float16")
    assert (
        without_gpu.supports(device="cuda", device_index=0, compute_type="float16")
        is False
    )


def test_cuda_probe_never_maps_device_one_onto_device_zero():
    module = SimpleNamespace(
        get_cuda_device_count=lambda: 2,
        get_supported_compute_types=lambda _device, index: (
            {"float16"} if index == 1 else set()
        ),
    )
    capabilities = FasterWhisperCapabilityProbe(
        module_loader=lambda _name: module
    ).inspect(topology(cuda(index=1)))

    assert (
        capabilities.supports(device="cuda", device_index=0, compute_type="float16")
        is False
    )
    assert capabilities.supports(device="cuda", device_index=1, compute_type="float16")


@pytest.mark.parametrize(
    "module",
    [
        SimpleNamespace(),
        SimpleNamespace(get_cuda_device_count=lambda: -1),
        SimpleNamespace(get_cuda_device_count=lambda: "bad"),
        SimpleNamespace(
            get_cuda_device_count=lambda: (_ for _ in ()).throw(RuntimeError("driver"))
        ),
    ],
)
def test_unusable_cuda_count_is_safely_treated_as_no_cuda(module):
    capabilities = FasterWhisperCapabilityProbe(
        module_loader=lambda _name: module
    ).inspect(topology(cuda()))
    assert tuple(target.device for target in capabilities.targets) == ("cpu",)


def test_absurd_cuda_count_is_bounded_before_runtime_queries():
    queried = []
    module = SimpleNamespace(
        get_cuda_device_count=lambda: 10_000,
        get_supported_compute_types=lambda _device, index: (
            queried.append(index) or {"float16"}
        ),
    )
    accelerators = tuple(cuda(index=index) for index in range(20))

    FasterWhisperCapabilityProbe(module_loader=lambda _name: module).inspect(
        topology(*accelerators)
    )

    assert queried == list(range(16))


@pytest.mark.parametrize(
    "reader",
    [
        None,
        lambda _device, _index: (_ for _ in ()).throw(RuntimeError("runtime")),
        lambda _device, _index: None,
    ],
)
def test_unusable_compute_type_reader_does_not_advertise_cuda(reader):
    module = SimpleNamespace(get_cuda_device_count=lambda: 1)
    if reader is not None:
        module.get_supported_compute_types = reader
    capabilities = FasterWhisperCapabilityProbe(
        module_loader=lambda _name: module
    ).inspect(topology(cuda()))
    assert tuple(target.device for target in capabilities.targets) == ("cpu",)


def test_compute_types_are_trimmed_deduplicated_and_sorted():
    module = SimpleNamespace(
        get_cuda_device_count=lambda: 1,
        get_supported_compute_types=lambda _device, _index: [
            " float16 ",
            "int8_float16",
            "float16",
            "",
        ],
    )
    target = (
        FasterWhisperCapabilityProbe(module_loader=lambda _name: module)
        .inspect(topology(cuda()))
        .targets[1]
    )
    assert target.compute_types == ("float16", "int8_float16")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"device": ""}, "execution target device cannot be empty"),
        ({"device_index": -1}, "execution target device_index cannot be negative"),
        ({"compute_types": ()}, "execution target compute_types cannot be empty"),
        (
            {"compute_types": ("int8", "int8")},
            "execution target compute_types must be unique",
        ),
        (
            {"device": "cpu", "accelerator_backend": AcceleratorBackend.CUDA},
            "CPU execution target cannot require an accelerator backend",
        ),
    ],
)
def test_execution_target_rejects_invalid_boundaries(kwargs, message):
    values = {
        "device": "cpu",
        "device_index": 0,
        "compute_types": ("int8",),
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=f"^{message}$"):
        EngineExecutionTarget(**values)


def test_capabilities_reject_empty_engine_and_duplicate_target_identity():
    target = EngineExecutionTarget("cpu", 0, ("int8",))
    with pytest.raises(ValueError, match="^engine capability name cannot be empty$"):
        EngineCapabilities("", (target,))
    with pytest.raises(
        ValueError, match="^engine execution target identities must be unique$"
    ):
        EngineCapabilities("engine", (target, target))


def test_registry_routes_by_engine_and_returns_empty_unknown_capability():
    class Provider:
        engine = "engine-a"

        def inspect(self, _topology):
            return EngineCapabilities(
                self.engine, (EngineExecutionTarget("cpu", 0, ("int8",)),)
            )

    registry = EngineCapabilityRegistry((Provider(),))
    assert registry.inspect("engine-a", topology()).targets
    assert registry.inspect("unknown", topology()) == EngineCapabilities("unknown", ())

    with pytest.raises(
        ValueError, match="^engine capability providers must be unique by engine$"
    ):
        EngineCapabilityRegistry((Provider(), Provider()))


@given(compute_type=st.text(min_size=1).filter(lambda value: value != "int8"))
def test_property_cpu_contract_never_claims_an_unadvertised_compute_type(compute_type):
    target = EngineExecutionTarget("cpu", 0, ("int8",))
    assert (
        target.supports(device="cpu", device_index=0, compute_type=compute_type)
        is False
    )
