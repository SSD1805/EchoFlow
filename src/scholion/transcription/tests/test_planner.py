from unittest.mock import Mock

import pytest

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.performance_tracker import PerformanceTracker
from scholion.interfaces.local_file_manager import LocalFileManager
from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from scholion.runner.models import ProcessingProfile, RunnerResources
from scholion.runner.policy import RunnerPolicyPlanner
from scholion.transcription.errors import ModelUnavailableError, ResourceAdmissionError
from scholion.transcription.models import DecodeStrategy
from scholion.transcription.planner import TranscriptionJobPlanner
from scholion.workspace.models import WorkspacePaths
from scholion.workspace.service import WorkspaceService

MIB = 1024**2
GIB = 1024**3
_DEFAULT_REGISTRY = object()


def runner_resources(memory=8 * GIB) -> RunnerResources:
    return RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=memory,
        memory_available_bytes=memory,
        memory_limit_bytes=None,
        effective_memory_available_bytes=memory,
        constraints=("cpu_affinity",),
    )


def media_info(
    source,
    *,
    duration=10.0,
    codec="aac",
    sample_rate=48_000,
    channels=2,
    container=None,
):
    return MediaInfo(
        InputIdentity(
            source, source.stat().st_size, source.stat().st_mtime_ns, "0" * 64
        ),
        container or ("wav" if codec.startswith("pcm") else "mov,mp4,m4a,3gp,3g2,mj2"),
        duration,
        (
            MediaStream(
                0,
                StreamKind.AUDIO,
                codec,
                duration,
                sample_rate,
                channels,
                "mono" if channels == 1 else "stereo",
            ),
        ),
        0,
    )


def build_planner(
    tmp_path,
    media,
    resources=None,
    *,
    model_registry=_DEFAULT_REGISTRY,
):
    paths = WorkspacePaths(
        tmp_path / "state",
        tmp_path / "cache",
        tmp_path / "cache/models",
        tmp_path / "output",
    )
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    workspace = WorkspaceService(paths, facade, id_factory=lambda: "plan-1")
    probe = Mock()
    probe.probe.return_value = media
    inspector = Mock()
    inspector.inspect.return_value = resources or runner_resources()
    registry = model_registry
    if registry is _DEFAULT_REGISTRY:
        registry = Mock()
        registry.resolved_revision.side_effect = lambda model_id: (
            f"{model_id}-managed-revision"
        )
    planner = TranscriptionJobPlanner(
        media_probe=probe,
        workspace_service=workspace,
        runner_inspector=inspector,
        policy_planner=RunnerPolicyPlanner(memory_budget_fraction=1),
        model_registry=registry,
    )
    return planner, paths, probe, inspector


def test_balanced_plan_composes_real_paths_media_cpu_engine_and_estimates(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"audio")
    media = media_info(source)
    planner, paths, probe, inspector = build_planner(tmp_path, media)

    plan = planner.plan(source)

    assert plan.schema_version == 1
    assert plan.job.job_id.value == "plan-1"
    assert plan.job.input_path == source.resolve()
    assert plan.job.workspace_dir == paths.jobs_dir / "plan-1"
    assert plan.artifact.path == paths.output_dir / "interview.json"
    assert plan.paths_reserved is False
    assert plan.media is media
    assert plan.runner is inspector.inspect.return_value
    assert plan.policy.profile is ProcessingProfile.BALANCED
    assert plan.policy.cpu_threads == 4
    assert plan.engine.engine == "faster-whisper"
    assert plan.engine.model == "small"
    assert plan.engine.device == "cpu"
    assert plan.engine.compute_type == "int8"
    assert plan.engine.beam_size == 5
    assert plan.engine.language is None
    assert plan.engine.model_cache_path == paths.model_dir / "faster-whisper"
    assert plan.engine.model_revision == "small-managed-revision"
    assert plan.decoder.strategy is DecodeStrategy.FFMPEG_NORMALIZE
    assert plan.decoder.output_codec == "pcm_s16le"
    assert plan.enhancement.enabled is False
    assert plan.segmentation.segment_duration_seconds == 600
    assert plan.segmentation.overlap_seconds == 0
    assert plan.segmentation.concurrency == 1
    assert plan.resources.private_workspace_bytes == 16 * MIB + 640_000
    assert plan.resources.public_output_bytes == 64 * 1024
    assert plan.resources.model_cache_bytes == 750 * MIB
    assert plan.resources.estimated_peak_memory_bytes == 2_304 * MIB
    assert plan.resources.fits_memory_budget is True
    assert plan.warnings == ("paths_are_unreserved",)
    probe.probe.assert_called_once_with(source.resolve())
    inspector.inspect.assert_called_once_with()
    assert not paths.state_dir.exists()
    assert not paths.cache_dir.exists()
    assert not paths.output_dir.exists()


def test_managed_model_revision_is_pinned_without_mutating_workspace(tmp_path):
    source = tmp_path / "managed.wav"
    source.write_bytes(b"audio")
    registry = Mock()
    registry.resolved_revision.return_value = "immutable-abc123"
    planner, paths, _, _ = build_planner(
        tmp_path,
        media_info(source),
        model_registry=registry,
    )

    plan = planner.plan(source)

    assert plan.engine.model == "small"
    assert plan.engine.model_revision == "immutable-abc123"
    registry.resolved_revision.assert_called_once_with("small")
    assert not paths.cache_dir.exists()


def test_missing_model_registry_fails_closed(tmp_path):
    source = tmp_path / "unconfigured.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(source),
        model_registry=None,
    )

    with pytest.raises(
        ModelUnavailableError, match="model management is not configured"
    ):
        planner.plan(source)


def test_unmanaged_selected_model_requires_explicit_install(tmp_path):
    source = tmp_path / "unmanaged.wav"
    source.write_bytes(b"audio")
    registry = Mock()
    registry.resolved_revision.return_value = None
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(source),
        model_registry=registry,
    )

    with pytest.raises(ModelUnavailableError, match="scholion models install small"):
        planner.plan(source)

    registry.resolved_revision.assert_called_once_with("small")


def test_screening_plan_is_provisional_compact_and_low_beam(tmp_path):
    source = tmp_path / "screen.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(tmp_path, media_info(source))

    plan = planner.plan(source, profile=ProcessingProfile.SCREENING)

    assert plan.policy.provisional is True
    assert plan.engine.model == "tiny"
    assert plan.engine.model_revision == "tiny-managed-revision"
    assert plan.engine.beam_size == 1
    assert plan.resources.model_cache_bytes == 150 * MIB
    assert plan.resources.estimated_peak_memory_bytes == 1_280 * MIB
    assert plan.warnings == (
        "paths_are_unreserved",
        "screening_output_is_provisional",
    )


def test_accuracy_plan_selects_medium_model_when_budget_allows(tmp_path):
    source = tmp_path / "accuracy.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path, media_info(source), runner_resources(8 * GIB)
    )
    plan = planner.plan(source, profile=ProcessingProfile.ACCURACY)
    assert plan.engine.model == "medium"
    assert plan.engine.model_revision == "medium-managed-revision"
    assert plan.resources.model_cache_bytes == 2_500 * MIB
    assert plan.resources.estimated_peak_memory_bytes == 4_352 * MIB
    assert plan.resources.fits_memory_budget is True


def test_enhancement_adds_full_private_derivative_and_provenance_contract(tmp_path):
    source = tmp_path / "enhance.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(
            source,
            duration=10,
            codec="pcm_s16le",
            sample_rate=16_000,
            channels=1,
        ),
    )

    raw = planner.plan(source)
    enhanced = planner.plan(source, enhance=True)

    assert raw.enhancement.enabled is False
    assert enhanced.enhancement.enabled is True
    assert enhanced.enhancement.provider == "ffmpeg-afftdn"
    assert (
        enhanced.resources.private_workspace_bytes
        - raw.resources.private_workspace_bytes
        == 320_000
    )
    assert "noise_suppression_enabled" in enhanced.warnings


def test_insufficient_compact_memory_is_refused_before_execution(tmp_path):
    source = tmp_path / "constrained.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path, media_info(source), runner_resources(1 * GIB)
    )

    with pytest.raises(
        ResourceAdmissionError,
        match="^No local transcription strategy fits the current safe memory budget$",
    ):
        planner.plan(source)


def test_peak_memory_equal_to_budget_is_feasible(tmp_path):
    source = tmp_path / "exact-memory.wav"
    source.write_bytes(b"audio")
    exact_budget = 1_280 * MIB
    planner, _, _, _ = build_planner(
        tmp_path, media_info(source), runner_resources(exact_budget)
    )
    plan = planner.plan(source)
    assert plan.engine.model == "tiny"
    assert plan.resources.estimated_peak_memory_bytes == exact_budget
    assert plan.resources.memory_budget_bytes == exact_budget
    assert plan.resources.fits_memory_budget is True


def test_explicit_feasible_strategy_overrides_profile_recommendation(tmp_path):
    source = tmp_path / "explicit.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(tmp_path, media_info(source))

    plan = planner.plan(
        source,
        profile=ProcessingProfile.SCREENING,
        strategy_id="medium-cpu-int8",
    )

    assert plan.engine.model == "medium"
    assert plan.engine.model_revision == "medium-managed-revision"
    assert plan.policy.provisional is True


def test_explicit_infeasible_strategy_is_not_silently_replaced(tmp_path):
    source = tmp_path / "explicit-constrained.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path, media_info(source), runner_resources(2 * GIB)
    )

    with pytest.raises(
        ResourceAdmissionError,
        match="^Selected transcription strategy exceeds the current safe memory budget$",
    ):
        planner.plan(source, strategy_id="medium-cpu-int8")


def test_strategy_assessment_reports_recommendation_and_rejections(tmp_path):
    source = tmp_path / "strategies.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path, media_info(source), runner_resources(3 * GIB)
    )

    assessments = planner.assess_strategies(profile=ProcessingProfile.BALANCED)

    assert tuple(item["strategy"]["strategy_id"] for item in assessments) == (
        "tiny-cpu-int8",
        "small-cpu-int8",
        "medium-cpu-int8",
    )
    assert tuple(item["feasible"] for item in assessments) == (True, True, False)
    assert tuple(item["recommended"] for item in assessments) == (False, True, False)
    assert assessments[2]["rejection_reasons"] == ["insufficient_memory"]


def test_long_recording_output_and_segment_estimates_scale_independently(tmp_path):
    source = tmp_path / "long.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(
            source,
            duration=1_000,
            codec="pcm_s16le",
            sample_rate=16_000,
            channels=1,
        ),
    )
    plan = planner.plan(source)
    assert plan.resources.public_output_bytes == 512_000
    assert plan.resources.private_workspace_bytes == 16 * MIB + 19_200_000


def test_exact_engine_ready_pcm_wav_uses_direct_decode_and_one_segment_temp(tmp_path):
    source = tmp_path / "ready.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(
            source,
            duration=2,
            codec="pcm_s16le",
            sample_rate=16_000,
            channels=1,
        ),
    )
    plan = planner.plan(source)
    assert plan.decoder.strategy is DecodeStrategy.DIRECT
    assert plan.resources.private_workspace_bytes == 16 * MIB + 64_000


def test_engine_ready_pcm_in_non_wav_container_is_normalized_before_segmentation(
    tmp_path,
):
    source = tmp_path / "pcm.mov"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(
        tmp_path,
        media_info(
            source,
            duration=2,
            codec="pcm_s16le",
            sample_rate=16_000,
            channels=1,
            container="mov,mp4,m4a,3gp,3g2,mj2",
        ),
    )
    plan = planner.plan(source)
    assert plan.decoder.strategy is DecodeStrategy.FFMPEG_NORMALIZE
    assert plan.resources.private_workspace_bytes == 16 * MIB + 128_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"codec": "pcm_s24le", "sample_rate": 16_000, "channels": 1},
        {"codec": "pcm_s16le", "sample_rate": 48_000, "channels": 1},
        {"codec": "pcm_s16le", "sample_rate": 16_000, "channels": 2},
    ],
)
def test_each_incompatible_audio_property_requires_normalization(tmp_path, overrides):
    source = tmp_path / "normalize.wav"
    source.write_bytes(b"audio")
    planner, _, _, _ = build_planner(tmp_path, media_info(source, **overrides))
    assert planner.plan(source).decoder.strategy is DecodeStrategy.FFMPEG_NORMALIZE


def test_output_override_and_existing_artifact_resolve_without_writes(tmp_path):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "consumer-output"
    output.mkdir()
    (output / "recording.json").write_text("keep")
    planner, _, _, _ = build_planner(tmp_path, media_info(source))

    plan = planner.plan(source, output_dir=output)

    assert plan.job.output_dir == output.resolve()
    assert plan.artifact.path == output / "recording-2.json"
    assert not plan.artifact.path.exists()
    assert (output / "recording.json").read_text() == "keep"
