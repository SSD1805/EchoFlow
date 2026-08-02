from echoflow.app.app_container import AppContainer
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.health_check import HealthCheck
from echoflow.interfaces.local_file_manager import LocalFileManager
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
