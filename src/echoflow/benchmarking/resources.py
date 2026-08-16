from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread

import psutil

_DEFAULT_SAMPLE_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class ProcessTreeObservation:
    """Sampled resource use for the EchoFlow process and current descendants."""

    sample_interval_seconds: float
    sample_count: int
    baseline_rss_bytes: int
    peak_rss_bytes: int
    mean_rss_bytes: float
    peak_cpu_percent: float
    mean_cpu_percent: float

    @property
    def peak_incremental_rss_bytes(self) -> int:
        return max(0, self.peak_rss_bytes - self.baseline_rss_bytes)

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_interval_seconds": self.sample_interval_seconds,
            "sample_count": self.sample_count,
            "baseline_rss_bytes": self.baseline_rss_bytes,
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_incremental_rss_bytes": self.peak_incremental_rss_bytes,
            "mean_rss_bytes": self.mean_rss_bytes,
            "peak_cpu_percent": self.peak_cpu_percent,
            "mean_cpu_percent": self.mean_cpu_percent,
            "cpu_percent_basis": "process_tree_sum",
            "rss_basis": "process_tree_rss_sum",
        }


@dataclass(frozen=True, slots=True)
class _Sample:
    rss_bytes: int
    cpu_percent: float


class ProcessTreeSampler:
    """Periodically sample the current process tree without transmitting data."""

    def __init__(
        self,
        sample_interval_seconds: float = _DEFAULT_SAMPLE_INTERVAL_SECONDS,
        process: psutil.Process | None = None,
    ):
        if sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive")
        self.sample_interval_seconds = sample_interval_seconds
        self.process = process or psutil.Process()
        self._samples: list[_Sample] = []
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("process sampler is already running")
        self._stop_event.clear()
        self._prime_cpu()
        self._append_sample()
        self._thread = Thread(target=self._run, name="echoflow-benchmark", daemon=True)
        self._thread.start()

    def stop(self) -> ProcessTreeObservation:
        if self._thread is None:
            raise RuntimeError("process sampler is not running")
        self._stop_event.set()
        self._thread.join()
        self._thread = None
        self._append_sample()
        return self._observation()

    def _run(self) -> None:
        while not self._stop_event.wait(self.sample_interval_seconds):
            self._append_sample()

    def _prime_cpu(self) -> None:
        for process in self._processes():
            try:
                process.cpu_percent(interval=None)
            except psutil.Error:
                continue

    def _append_sample(self) -> None:
        rss_bytes = 0
        cpu_percent = 0.0
        observed = False
        for process in self._processes():
            try:
                rss_bytes += process.memory_info().rss
                cpu_percent += max(0.0, process.cpu_percent(interval=None))
                observed = True
            except psutil.Error:
                continue
        if observed:
            self._samples.append(_Sample(rss_bytes, cpu_percent))

    def _processes(self) -> list[psutil.Process]:
        try:
            return [self.process, *self.process.children(recursive=True)]
        except psutil.Error:
            return [self.process]

    def _observation(self) -> ProcessTreeObservation:
        if not self._samples:
            return ProcessTreeObservation(
                sample_interval_seconds=self.sample_interval_seconds,
                sample_count=0,
                baseline_rss_bytes=0,
                peak_rss_bytes=0,
                mean_rss_bytes=0.0,
                peak_cpu_percent=0.0,
                mean_cpu_percent=0.0,
            )
        rss_values = [sample.rss_bytes for sample in self._samples]
        cpu_values = [sample.cpu_percent for sample in self._samples]
        return ProcessTreeObservation(
            sample_interval_seconds=self.sample_interval_seconds,
            sample_count=len(self._samples),
            baseline_rss_bytes=rss_values[0],
            peak_rss_bytes=max(rss_values),
            mean_rss_bytes=sum(rss_values) / len(rss_values),
            peak_cpu_percent=max(cpu_values),
            mean_cpu_percent=sum(cpu_values) / len(cpu_values),
        )
