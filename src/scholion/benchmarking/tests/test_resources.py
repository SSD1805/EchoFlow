import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

from scholion.benchmarking.resources import ProcessTreeSampler


class FakeProcess:
    def __init__(
        self,
        rss: int,
        cpu_values: list[float],
        children: list["FakeProcess"] | None = None,
        *,
        fail_children: bool = False,
        fail_sample: bool = False,
    ) -> None:
        self.rss = rss
        self.cpu_values = list(cpu_values)
        self._children = children or []
        self.fail_children = fail_children
        self.fail_sample = fail_sample

    def children(self, *, recursive: bool) -> list["FakeProcess"]:
        assert recursive is True
        if self.fail_children:
            raise psutil.AccessDenied(pid=1)
        return self._children

    def memory_info(self):
        if self.fail_sample:
            raise psutil.NoSuchProcess(pid=2)
        return SimpleNamespace(rss=self.rss)

    def cpu_percent(self, interval=None) -> float:
        assert interval is None
        if self.fail_sample:
            raise psutil.NoSuchProcess(pid=2)
        if self.cpu_values:
            return self.cpu_values.pop(0)
        return 0.0


def test_sampler_collects_process_tree_rss_and_cpu_without_external_io():
    child = FakeProcess(300, [0.0, 25.0, 30.0])
    root = FakeProcess(700, [0.0, 50.0, 60.0], [child])
    sampler = ProcessTreeSampler(sample_interval_seconds=10.0, process=root)

    sampler.start()
    observation = sampler.stop()

    assert observation.sample_count == 2
    assert observation.baseline_rss_bytes == 1000
    assert observation.peak_rss_bytes == 1000
    assert observation.peak_incremental_rss_bytes == 0
    assert observation.mean_rss_bytes == 1000
    assert observation.peak_cpu_percent == 90.0
    assert observation.mean_cpu_percent == 82.5
    assert observation.to_dict()["cpu_percent_basis"] == "process_tree_sum"


def test_sampler_observes_a_real_python_child_process():
    sampler = ProcessTreeSampler(sample_interval_seconds=0.02)
    sampler.start()
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "import time; "
                "payload = bytearray(16 * 1024 * 1024); "
                "time.sleep(0.3); "
                "assert payload[0] == 0"
            ),
        ],
        check=True,
    )
    observation = sampler.stop()

    assert observation.sample_count >= 2
    assert observation.baseline_rss_bytes > 0
    assert observation.peak_rss_bytes > observation.baseline_rss_bytes
    assert observation.peak_incremental_rss_bytes > 0
    assert observation.mean_rss_bytes > 0


def test_sampler_ignores_disappearing_children_and_child_enumeration_failure():
    disappearing = FakeProcess(100, [0.0], fail_sample=True)
    root = FakeProcess(500, [0.0, 10.0, 20.0], [disappearing])
    sampler = ProcessTreeSampler(sample_interval_seconds=10.0, process=root)

    sampler.start()
    observation = sampler.stop()

    assert observation.peak_rss_bytes == 500

    root.fail_children = True
    sampler = ProcessTreeSampler(sample_interval_seconds=10.0, process=root)
    sampler.start()
    fallback = sampler.stop()
    assert fallback.peak_rss_bytes == 500


def test_sampler_state_and_interval_are_validated():
    with pytest.raises(ValueError, match="positive"):
        ProcessTreeSampler(sample_interval_seconds=0)

    root = FakeProcess(1, [0.0, 0.0, 0.0])
    sampler = ProcessTreeSampler(sample_interval_seconds=10.0, process=root)
    with pytest.raises(RuntimeError, match="not running"):
        sampler.stop()

    sampler.start()
    with pytest.raises(RuntimeError, match="already running"):
        sampler.start()
    sampler.stop()
