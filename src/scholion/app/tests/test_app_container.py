from pathlib import Path
from unittest.mock import Mock

import pytest

from scholion.app.app_container import AppContainer, _ModelStorageAdmitter
from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.health_check import HealthCheck
from scholion.interfaces.local_file_manager import LocalFileManager
from scholion.media.probe import FfprobeMediaProbe
from scholion.model_management.errors import ModelManagementError
from scholion.model_management.service import ModelManager
from scholion.runner.inspector import RunnerInspector
from scholion.runner.policy import RunnerPolicyPlanner
from scholion.transcription.assembly import TranscriptAssembler
from scholion.transcription.audio import FfmpegAudioDecoder
from scholion.transcription.backend import FasterWhisperTranscriber
from scholion.transcription.errors import ResourceAdmissionError
from scholion.transcription.executor import TranscriptionExecutor
from scholion.transcription.planner import TranscriptionJobPlanner
from scholion.transcription.segmentation import WaveAudioSegmenter
from scholion.transcription.storage import StorageAllocation
from scholion.workspace.service import WorkspaceService


def test_container_resolves_two_layer_local_storage_graph():
    container = AppContainer()
    facade = container.file_manager()
    assert isinstance(facade, FileManagerFacade)
    assert isinstance(container.local_file_manager(), LocalFileManager)
    assert facade.file_manager is container.local_file_manager()
    assert facade.tracker is container.performance_tracker()


def test_container_builds_diagnostics_from_the_same_config():
    container = AppContainer()
    diagnostics = container.health_check()
    assert isinstance(diagnostics, HealthCheck)
    assert diagnostics.probes[0].workspace == container.config().STATE_DIR


def test_container_resolves_workspace_service_from_the_storage_graph():
    container = AppContainer()
    service = container.workspace_service()
    assert isinstance(service, WorkspaceService)
    assert service.file_manager is container.file_manager()
    assert service.paths is container.workspace_paths()


def test_container_resolves_runner_inspection_and_policy_from_config():
    container = AppContainer()
    assert isinstance(container.runner_inspector(), RunnerInspector)
    assert isinstance(container.runner_policy_planner(), RunnerPolicyPlanner)
    assert (
        container.runner_policy_planner().memory_budget_fraction
        == container.config().MEMORY_BUDGET_FRACTION
    )


def test_container_composes_model_manager_with_planner_registry():
    container = AppContainer()
    manager = container.model_manager()
    planner = container.transcription_planner()

    assert isinstance(manager, ModelManager)
    assert manager.file_store is container.file_manager()
    assert manager.storage_admitter is container.model_storage_admitter()
    assert planner.model_registry is manager


def test_model_storage_adapter_reuses_shared_disk_policy():
    policy = Mock()
    admitter = _ModelStorageAdmitter(policy)
    path = Path("models")

    admitter.admit(path, 123)

    policy.admit.assert_called_once_with((StorageAllocation(path, 123),))


def test_model_storage_adapter_translates_disk_failure():
    policy = Mock()
    policy.admit.side_effect = ResourceAdmissionError("job-oriented detail")
    admitter = _ModelStorageAdmitter(policy)

    with pytest.raises(ModelManagementError, match="planned model allocation"):
        admitter.admit(Path("models"), 123)


def test_container_composes_media_probe_and_transcription_planner():
    container = AppContainer()
    assert isinstance(container.media_probe(), FfprobeMediaProbe)
    assert (
        container.media_probe().timeout_seconds
        == container.config().FFPROBE_TIMEOUT_SECONDS
    )
    planner = container.transcription_planner()
    assert isinstance(planner, TranscriptionJobPlanner)
    assert planner.media_probe is container.media_probe()
    assert planner.workspace_service is container.workspace_service()
    assert planner.runner_inspector is container.runner_inspector()
    assert planner.policy_planner is container.runner_policy_planner()


def test_container_composes_per_execution_audio_segmentation_and_engine_services():
    container = AppContainer()
    first = container.transcription_executor()
    second = container.transcription_executor()
    assert isinstance(first, TranscriptionExecutor)
    assert isinstance(first.audio_decoder, FfmpegAudioDecoder)
    assert isinstance(first.audio_segmenter, WaveAudioSegmenter)
    assert isinstance(first.transcriber, FasterWhisperTranscriber)
    assert isinstance(first.transcript_assembler, TranscriptAssembler)
    assert first is not second
    assert first.audio_segmenter is not second.audio_segmenter
    assert first.transcriber is not second.transcriber
    assert first.transcript_assembler is not second.transcript_assembler
    assert first.workspace_service is container.workspace_service()
    assert first.file_manager is container.file_manager()
    assert first.logger is container.logger()
