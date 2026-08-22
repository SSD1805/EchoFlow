import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scholion.runner.inspector import (
    RunnerInspector,
    _affinity_count,
    _cpu_quota_cores,
    _finite_bytes,
    _read_text,
)


def _inspector(*, texts, logical=16, physical=8, affinity=8, available=20, total=32):
    def cpu_count(is_logical):
        return logical if is_logical else physical

    return RunnerInspector(
        cpu_count=cpu_count,
        virtual_memory=lambda: SimpleNamespace(
            available=available * 1024**3, total=total * 1024**3
        ),
        affinity_count=lambda: affinity,
        text_reader=lambda path: texts.get(path.name),
        platform_name=lambda: "TestOS",
        machine_name=lambda: "test-machine",
    )


def test_inspector_respects_affinity_cpu_quota_and_memory_limit():
    inspector = _inspector(
        texts={
            "cpu.max": "250000 100000",
            "memory.max": str(8 * 1024**3),
            "memory.current": str(2 * 1024**3),
        }
    )

    resources = inspector.inspect()

    assert resources.platform == "TestOS"
    assert resources.machine == "test-machine"
    assert resources.logical_cpus == 16
    assert resources.physical_cpus == 8
    assert resources.affinity_cpus == 8
    assert resources.cpu_quota_cores == 2.5
    assert resources.effective_cpus == 2
    assert resources.effective_memory_available_bytes == 6 * 1024**3
    assert resources.memory_limit_bytes == 8 * 1024**3
    assert resources.constraints == ("cpu_affinity", "cpu_quota", "memory_limit")


def test_unlimited_or_unreadable_cgroups_fall_back_to_process_visible_resources():
    resources = _inspector(
        texts={"cpu.max": "max 100000", "memory.max": "max"},
        logical=4,
        physical=None,
        affinity=None,
        available=3,
        total=4,
    ).inspect()

    assert resources.effective_cpus == 4
    assert resources.effective_memory_available_bytes == 3 * 1024**3
    assert resources.memory_limit_bytes is None
    assert resources.constraints == ()


def test_malformed_cgroup_values_are_ignored_safely():
    resources = _inspector(
        texts={
            "cpu.max": "not-a-quota",
            "memory.max": "not-bytes",
            "memory.current": "also-not-bytes",
        },
        logical=2,
        affinity=2,
        available=1,
        total=2,
    ).inspect()

    assert resources.cpu_quota_cores is None
    assert resources.memory_limit_bytes is None
    assert resources.effective_cpus == 2
    assert resources.effective_memory_available_bytes == 1024**3


def test_memory_limit_without_current_usage_is_still_a_conservative_ceiling():
    resources = _inspector(
        texts={"memory.max": str(4 * 1024**3)}, available=10, total=16
    ).inspect()

    assert resources.effective_memory_available_bytes == 4 * 1024**3
    assert resources.constraints == ("cpu_affinity", "memory_limit")


def test_missing_cpu_count_never_produces_zero_effective_cpus():
    resources = _inspector(
        texts={}, logical=None, physical=None, affinity=None, available=1, total=1
    ).inspect()
    assert resources.logical_cpus == 1
    assert resources.effective_cpus == 1


def test_negative_cpu_count_is_defensively_normalized_to_one():
    resources = _inspector(
        texts={}, logical=-1, physical=None, affinity=None, available=1, total=1
    ).inspect()
    assert resources.logical_cpus == 1
    assert resources.effective_cpus == 1


def test_affinity_alone_limits_effective_cpu_count():
    resources = _inspector(
        texts={"cpu.max": "max 100000"}, logical=8, affinity=3
    ).inspect()
    assert resources.effective_cpus == 3
    assert resources.constraints == ("cpu_affinity",)


def test_equal_affinity_and_quota_are_not_reported_as_constraints():
    resources = _inspector(
        texts={"cpu.max": "400000 100000"}, logical=4, affinity=4
    ).inspect()
    assert resources.effective_cpus == 4
    assert resources.constraints == ()


def test_fractional_cpu_quota_below_one_still_allows_one_thread():
    resources = _inspector(
        texts={"cpu.max": "50000 100000"}, logical=8, affinity=8
    ).inspect()
    assert resources.cpu_quota_cores == 0.5
    assert resources.effective_cpus == 1
    assert resources.constraints == ("cpu_quota",)


def test_exhausted_memory_cgroup_reports_zero_available():
    resources = _inspector(
        texts={
            "memory.max": str(4 * 1024**3),
            "memory.current": str(5 * 1024**3),
        },
        available=10,
        total=16,
    ).inspect()
    assert resources.effective_memory_available_bytes == 0
    assert resources.constraints == ("cpu_affinity", "memory_limit")


def test_equal_memory_ceiling_is_not_reported_as_a_constraint():
    resources = _inspector(
        texts={
            "memory.max": str(5 * 1024**3),
            "memory.current": str(2 * 1024**3),
        },
        logical=4,
        affinity=4,
        available=3,
        total=8,
    ).inspect()
    assert resources.effective_memory_available_bytes == 3 * 1024**3
    assert resources.constraints == ()


def test_default_virtual_memory_provider_is_used_when_not_injected():
    memory = SimpleNamespace(available=1234, total=5678)
    with patch(
        "scholion.runner.inspector.psutil.virtual_memory", return_value=memory
    ) as virtual_memory:
        resources = RunnerInspector(
            cpu_count=lambda _logical: 2,
            affinity_count=lambda: 2,
            text_reader=lambda _path: None,
            platform_name=lambda: "TestOS",
            machine_name=lambda: "test-machine",
        ).inspect()
    virtual_memory.assert_called_once_with()
    assert resources.memory_available_bytes == 1234
    assert resources.memory_total_bytes == 5678


def test_text_reader_strips_utf8_and_returns_none_for_io_or_unicode_errors(tmp_path):
    valid = tmp_path / "valid"
    valid.write_text("  100 200\n", encoding="utf-8")
    invalid = tmp_path / "invalid"
    invalid.write_bytes(b"\xff")
    assert _read_text(valid) == "100 200"
    assert _read_text(tmp_path / "missing") is None
    assert _read_text(invalid) is None


def test_affinity_reader_uses_current_process_and_handles_os_errors(monkeypatch):
    calls = []

    def affinity(process_id):
        calls.append(process_id)
        return {1, 2, 3}

    monkeypatch.setattr(os, "sched_getaffinity", affinity, raising=False)
    assert _affinity_count() == 3
    assert calls == [0]

    monkeypatch.setattr(
        os, "sched_getaffinity", lambda _process_id: set(), raising=False
    )
    assert _affinity_count() is None

    def unavailable(_process_id):
        raise OSError("unsupported")

    monkeypatch.setattr(os, "sched_getaffinity", unavailable, raising=False)
    assert _affinity_count() is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("max 100000", None),
        ("100000", None),
        ("100000 max", None),
        ("bad 100000", None),
        ("0 100000", None),
        ("-1 100000", None),
        ("100000 0", None),
        ("100000 -1", None),
        ("1 1", 1.0),
        ("250000 100000", 2.5),
    ],
)
def test_cpu_quota_parser_has_explicit_boundary_behavior(value, expected):
    assert _cpu_quota_cores(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("max", None),
        ("bad", None),
        ("-1", None),
        ("0", None),
        ("1", 1),
        ("2048", 2048),
    ],
)
def test_finite_byte_parser_has_explicit_boundary_behavior(value, expected):
    assert _finite_bytes(value) == expected
