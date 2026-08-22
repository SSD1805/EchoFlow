import json
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scholion.benchmarking.models import BenchmarkRunError, BenchmarkStatus
from scholion.benchmarking.resources import ProcessTreeObservation
from scholion.benchmarking.runner import BenchmarkRunner, _scholion_version
from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.performance_tracker import PerformanceTracker
from scholion.interfaces.local_file_manager import LocalFileManager
from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from scholion.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from scholion.transcription.models import (
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineProvenance,
    RecognizedSegment,
    ResourceEstimate,
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from scholion.workspace.models import Artifact, ArtifactKind, Job, JobId, WorkspacePaths
from scholion.workspace.service import WorkspaceService

MIB = 1024**2
GIB = 1024**3


class StepClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


class FakeSampler:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> ProcessTreeObservation:
        assert self.started
        return ProcessTreeObservation(
            sample_interval_seconds=0.25,
            sample_count=4,
            baseline_rss_bytes=100 * MIB,
            peak_rss_bytes=500 * MIB,
            mean_rss_bytes=300 * MIB,
            peak_cpu_percent=250.0,
            mean_cpu_percent=150.0,
        )


def _plan(tmp_path: Path) -> tuple[TranscriptionJobPlan, WorkspacePaths]:
    source = tmp_path / "participant-secret-name.wav"
    source.write_bytes(b"private-audio")
    paths = WorkspacePaths(
        tmp_path / "state",
        tmp_path / "cache",
        tmp_path / "cache" / "models",
        tmp_path / "output",
    )
    job = Job(JobId("job-1"), source, paths.jobs_dir / "job-1", paths.output_dir)
    media = MediaInfo(
        InputIdentity(
            source.resolve(),
            source.stat().st_size,
            source.stat().st_mtime_ns,
            "a" * 64,
        ),
        "wav",
        10.0,
        (MediaStream(0, StreamKind.AUDIO, "pcm_s16le", 10.0, 16_000, 1),),
        0,
    )
    runner = RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=8 * GIB,
        memory_available_bytes=6 * GIB,
        memory_limit_bytes=None,
        effective_memory_available_bytes=6 * GIB,
    )
    policy = ExecutionPolicy(
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        cpu_threads=4,
        memory_budget_bytes=4 * GIB,
    )
    engine = CpuEngineConfiguration(
        "faster-whisper",
        "small",
        "cpu",
        "int8",
        4,
        5,
        None,
        paths.model_dir / "faster-whisper" / "small",
        "revision-1",
    )
    artifact = Artifact(
        job.job_id,
        ArtifactKind.CANONICAL_JSON,
        paths.output_dir / "participant-secret-name.json",
    )
    estimate = ResourceEstimate(
        private_workspace_bytes=16 * MIB,
        public_output_bytes=64 * 1024,
        model_cache_bytes=750 * MIB,
        estimated_peak_memory_bytes=2_304 * MIB,
        memory_budget_bytes=4 * GIB,
        fits_memory_budget=True,
    )
    return (
        TranscriptionJobPlan(
            job=job,
            artifact=artifact,
            media=media,
            runner=runner,
            policy=policy,
            engine=engine,
            decoder=DecodeConfiguration(
                DecodeStrategy.DIRECT,
                "pcm_s16le",
                16_000,
                1,
            ),
            resources=estimate,
            warnings=("paths_are_unreserved",),
        ),
        paths,
    )


def _result(
    plan: TranscriptionJobPlan, artifact: Artifact
) -> TranscriptionExecutionResult:
    transcript = CanonicalTranscript(
        job_id=plan.job.job_id.value,
        source=TranscriptSource.from_media(plan.media),
        profile=plan.policy.profile,
        provisional=plan.policy.provisional,
        decode_strategy=plan.decoder.strategy,
        engine=EngineProvenance.from_engine(plan.engine, "1.2.1"),
        detected_language="en",
        language_probability=0.99,
        segments=(RecognizedSegment(0, 0.0, 10.0, "Synthetic transcript."),),
    )
    return TranscriptionExecutionResult(plan.job, artifact, transcript)


def _runner(
    paths: WorkspacePaths,
) -> tuple[BenchmarkRunner, FileManagerFacade, WorkspaceService]:
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    workspace = WorkspaceService(paths, facade, id_factory=lambda: "unused")
    runner = BenchmarkRunner(
        file_manager=facade,
        workspace_service=workspace,
        sampler_factory=FakeSampler,
        clock=StepClock(),
        id_factory=lambda: "benchmark-1",
        version_factory=lambda: "0.1.0",
        python_version_factory=lambda: "3.12.0",
    )
    return runner, facade, workspace


def test_completed_run_persists_path_minimized_extensible_report(tmp_path):
    plan, paths = _plan(tmp_path)
    runner, facade, workspace = _runner(paths)

    def execute(observer):
        job = workspace.create_job(
            plan.job.input_path,
            output_dir=plan.job.output_dir,
            job_id=plan.job.job_id,
        )
        artifact = workspace.reserve_artifact(job, ArtifactKind.CANONICAL_JSON)
        with observer.span("segment.transcribe"):
            observer.record_value("segments.total", 1)
            observer.record_value("segments.completed", 1)
        facade.save_file(b'{"transcript":true}\n', artifact.path)
        return _result(plan, artifact)

    result = runner.run(plan, execute=execute, planning_wall_seconds=0.5)

    assert result.report.status is BenchmarkStatus.COMPLETED
    assert result.report.source.sha256 == "a" * 64
    assert result.report.process_tree.peak_rss_bytes == 500 * MIB
    assert result.report.canonical_artifact_bytes == len(b'{"transcript":true}\n')
    assert result.report.values == {"segments.completed": 1, "segments.total": 1}
    assert result.report.stages[0].name == "segment.transcribe"
    assert result.report.to_dict()["execution_contract"]["engine"]["model"] == "small"

    serialized = result.report_path.read_text()
    assert str(plan.job.input_path) not in serialized
    assert plan.job.input_path.name not in serialized
    assert str(plan.engine.model_cache_path) not in serialized
    assert "model_cache_path" not in serialized
    assert json.loads(serialized)["source"]["sha256"] == "a" * 64
    assert result.to_dict()["benchmark_report_path"] == str(result.report_path)


def test_keyboard_interrupt_persists_partial_report_and_retains_error_type(tmp_path):
    plan, paths = _plan(tmp_path)
    runner, _, _ = _runner(paths)

    def execute(observer):
        with observer.span("segment.transcribe"):
            observer.record_value("segments.completed", 1)
            raise KeyboardInterrupt()

    with pytest.raises(BenchmarkRunError) as raised:
        runner.run(plan, execute=execute)

    error = raised.value
    assert error.status is BenchmarkStatus.INTERRUPTED
    document = json.loads(error.report_path.read_text())
    assert document["status"] == "interrupted"
    assert document["error_type"] == "KeyboardInterrupt"
    assert document["observed"]["values"]["segments.completed"] == 1
    assert document["observed"]["stages"][0]["failed_count"] == 1


def test_failed_run_persists_type_without_exception_message(tmp_path):
    plan, paths = _plan(tmp_path)
    runner, _, _ = _runner(paths)

    def execute(_observer):
        raise RuntimeError("private participant name leaked here")

    with pytest.raises(BenchmarkRunError) as raised:
        runner.run(plan, execute=execute, resume=True)

    document = raised.value.report_path.read_text()
    parsed = json.loads(document)
    assert parsed["status"] == "failed"
    assert parsed["resume"] is True
    assert parsed["error_type"] == "RuntimeError"
    assert "private participant name leaked here" not in document


def test_uninstalled_package_version_has_safe_fallback():
    with patch(
        "scholion.benchmarking.runner.version",
        side_effect=PackageNotFoundError("scholion"),
    ):
        assert _scholion_version() == "0+unknown"
