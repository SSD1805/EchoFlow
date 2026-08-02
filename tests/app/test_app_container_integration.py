from src.app.app_container import AppContainer
from src.core.file_manager_facade import FileManagerFacade
from src.core.ilogger import ILogger
from src.interfaces.local_file_manager import LocalFileManager
from tests.factories import AppConfigFactory


def test_container_resolves_complete_local_file_graph(tmp_path):
    container = AppContainer()
    container.config.override(AppConfigFactory(LOG_LEVEL="DEBUG"))

    facade = container.file_manager()
    path = tmp_path / "nested" / "recording.bin"
    facade.ensure_directory_exists(str(path.parent))
    facade.save_file(b"audio-bytes", str(path))

    assert isinstance(container.logger(), ILogger)
    assert isinstance(container.local_file_manager(), LocalFileManager)
    assert isinstance(facade, FileManagerFacade)
    assert facade.file_manager is container.local_file_manager()
    assert facade.file_exists(str(path))
    assert path.read_bytes() == b"audio-bytes"


def test_container_health_check_uses_real_workspace_probe(tmp_path):
    container = AppContainer()
    container.config.override(
        AppConfigFactory(
            WORKSPACE_DIR=tmp_path,
            MIN_FREE_DISK_BYTES=0,
            WARN_FREE_DISK_BYTES=0,
        )
    )
    report = container.health_check().run()
    workspace = next(check for check in report.checks if check.check_id == "workspace")
    assert workspace.status.value == "pass"
