from echoflow.app.app_container import AppContainer
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.health_check import HealthCheck
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.probe import FfprobeMediaProbe
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.workspace.service import WorkspaceService


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
