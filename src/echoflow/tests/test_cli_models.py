import json
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from echoflow.cli import app
from echoflow.core.config import AppConfig
from echoflow.model_management.errors import ModelManagementError
from echoflow.model_management.models import (
    ManagedModelManifest,
    ModelInventoryItem,
    ModelSpec,
)
from echoflow.runner.models import ProcessingProfile

runner = CliRunner()


class Provider:
    def __init__(self, value):
        self.value = value

    def __call__(self, *args, **kwargs):
        del args, kwargs
        return self.value


class FakeContainer:
    def __init__(self) -> None:
        self.config = Provider(
            AppConfig(
                STATE_DIR=Path("state"),
                CACHE_DIR=Path("cache"),
                MODEL_DIR=Path("cache/models"),
                OUTPUT_DIR=Path("output"),
                MIN_FREE_DISK_BYTES=0,
                WARN_FREE_DISK_BYTES=0,
                _env_file=None,
            )
        )
        self.model_manager = Provider(Mock())
        self.transcription_planner = Provider(Mock())


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="small",
        engine="faster-whisper",
        repository_id="Systran/faster-whisper-small",
        estimated_cache_bytes=750 * 1024**2,
        quality_rank=2,
        required_files=("model.bin", "config.json", "tokenizer.json"),
    )


def _manifest() -> ManagedModelManifest:
    return ManagedModelManifest(
        schema_version=1,
        model_id="small",
        engine="faster-whisper",
        repository_id="Systran/faster-whisper-small",
        requested_revision="release-v1",
        resolved_revision="abc123",
        snapshot_path=Path("cache/models/faster-whisper/snapshots/abc123"),
        size_bytes=700 * 1024**2,
        verification="huggingface_snapshot_required_files_v1",
    )


def _invoke(container: FakeContainer, *arguments: str):
    with patch("echoflow.cli.AppContainer", return_value=container):
        return runner.invoke(app, ["models", *arguments])


def test_root_help_exposes_models_group() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "models" in result.output


def test_models_json_reports_offline_inventory() -> None:
    container = FakeContainer()
    container.model_manager().inventory.return_value = (ModelInventoryItem(_spec()),)

    result = _invoke(container, "--json")

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["spec"]["model_id"] == "small"
    assert payload[0]["installed"] is False
    container.model_manager().inventory.assert_called_once_with()


def test_models_install_passes_revision_and_emits_manifest_json() -> None:
    container = FakeContainer()
    container.model_manager().install.return_value = _manifest()

    result = _invoke(
        container,
        "install",
        "small",
        "--revision",
        "release-v1",
        "--json",
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["resolved_revision"] == "abc123"
    assert payload["verification"] == "huggingface_snapshot_required_files_v1"
    container.model_manager().install.assert_called_once_with(
        "small", revision="release-v1"
    )


def test_models_remove_yes_deletes_exact_managed_model() -> None:
    container = FakeContainer()
    container.model_manager().is_installed.return_value = True
    container.model_manager().remove.return_value = _manifest()

    result = _invoke(container, "remove", "small", "--yes", "--json")

    assert result.exit_code == 0
    assert json.loads(result.stdout)["removed"]["resolved_revision"] == "abc123"
    container.model_manager().is_installed.assert_called_once_with("small")
    container.model_manager().remove.assert_called_once_with("small")


def test_models_recommend_reuses_strategy_planner_and_reports_install_command() -> None:
    container = FakeContainer()
    container.transcription_planner().assess_strategies.return_value = (
        {
            "recommended": True,
            "strategy": {
                "model": "small",
                "device": "cpu",
                "compute_type": "int8",
            },
        },
    )
    container.model_manager().is_installed.return_value = False

    result = _invoke(container, "recommend")

    assert result.exit_code == 0
    assert "small" in result.output
    assert "echoflow models install small" in result.output
    container.transcription_planner().assess_strategies.assert_called_once_with(
        profile=ProcessingProfile.BALANCED
    )


def test_models_recommend_fails_typed_when_no_strategy_is_safe() -> None:
    container = FakeContainer()
    container.transcription_planner().assess_strategies.return_value = (
        {"recommended": False, "strategy": {"model": "tiny"}},
    )

    result = _invoke(container, "recommend")

    assert result.exit_code == 2
    assert "No safe local model recommendation" in result.stderr
    container.model_manager().is_installed.assert_not_called()


def test_models_install_surfaces_public_model_error() -> None:
    container = FakeContainer()
    container.model_manager().install.side_effect = ModelManagementError(
        "The selected model could not be downloaded and verified"
    )

    result = _invoke(container, "install", "small")

    assert result.exit_code == 2
    assert "downloaded and verified" in result.stderr
