from echoflow.app.app_container import AppContainer
from echoflow.core.config import AppConfig
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.ilogger import ILogger
from echoflow.core.privacy import PathDisclosure
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.probe import FfprobeMediaProbe


def _test_config(tmp_path, **overrides) -> AppConfig:
    values = {
        "APP_ENV": "test",
        "DEBUG": False,
        "LOG_LEVEL": "INFO",
        "STATE_DIR": tmp_path / "state",
        "CACHE_DIR": tmp_path / "cache",
        "MODEL_DIR": tmp_path / "cache" / "models",
        "OUTPUT_DIR": tmp_path / "Downloads" / "EchoFlow",
        "MIN_FREE_DISK_BYTES": 0,
        "WARN_FREE_DISK_BYTES": 0,
        "FFMPEG_TIMEOUT_SECONDS": 0.1,
    }
    values.update(overrides)
    return AppConfig(**values)


def test_container_resolves_complete_local_file_graph(tmp_path):
    container = AppContainer()
    container.config.override(_test_config(tmp_path, LOG_LEVEL="DEBUG"))

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
    container.config.override(_test_config(tmp_path))
    container.workspace_service().initialize()
    report = container.health_check().run()
    workspace = next(check for check in report.checks if check.check_id == "workspace")
    assert workspace.status.value == "pass"


def test_container_initializes_private_and_public_paths_without_mixing_them(tmp_path):
    container = AppContainer()
    container.config.override(_test_config(tmp_path))

    paths = container.workspace_service().initialize()

    assert paths.jobs_dir.is_dir()
    assert paths.model_dir.is_dir()
    assert paths.output_dir.is_dir()
    assert not paths.output_dir.is_relative_to(paths.state_dir)


def test_container_defaults_to_path_redaction_in_file_operation_logs(tmp_path):
    container = AppContainer()
    container.config.override(_test_config(tmp_path, LOG_PATHS=PathDisclosure.REDACT))
    facade = container.file_manager()
    assert facade.path_disclosure is PathDisclosure.REDACT


def test_container_applies_configured_media_probe_timeout(tmp_path):
    container = AppContainer()
    container.config.override(_test_config(tmp_path, FFPROBE_TIMEOUT_SECONDS=7.5))
    probe = container.media_probe()
    assert isinstance(probe, FfprobeMediaProbe)
    assert probe.timeout_seconds == 7.5
