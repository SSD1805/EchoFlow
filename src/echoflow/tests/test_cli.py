import json
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from echoflow.cli import app
from echoflow.core.config import AppConfig
from echoflow.core.health_check import (
    CheckResult,
    CheckStatus,
    HealthReport,
    OverallStatus,
)
from echoflow.media.errors import UnsupportedMediaError
from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import (
    ExecutionPolicy,
    ModelTier,
    ProcessingProfile,
    RunnerResources,
)
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    ResourceEstimate,
    TranscriptionJobPlan,
)
from echoflow.workspace.errors import InvalidInputError, UnsafePathError
from echoflow.workspace.models import (
    Artifact,
    ArtifactKind,
    Job,
    JobId,
    WorkspacePaths,
)

runner = CliRunner()


def report(status: OverallStatus) -> HealthReport:
    check_status = {
        OverallStatus.HEALTHY: CheckStatus.PASS,
        OverallStatus.DEGRADED: CheckStatus.WARN,
        OverallStatus.UNHEALTHY: CheckStatus.FAIL,
    }[status]
    return HealthReport(
        status,
        (
            CheckResult(
                "workspace",
                check_status,
                "workspace result",
                status is not OverallStatus.DEGRADED,
            ),
        ),
    )


class Provider:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def override(self, value):
        self.value = value


class FakeContainer:
    def __init__(self, health_report):
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
        service = Mock()
        service.run.return_value = health_report
        self.health_check = Provider(service)
        workspace_service = Mock()
        workspace_service.initialize.return_value = WorkspacePaths(
            state_dir=Path("state"),
            cache_dir=Path("cache"),
            model_dir=Path("cache/models"),
            output_dir=Path("output"),
        )
        self.workspace_service = Provider(workspace_service)
        resources = RunnerResources(
            platform="TestOS",
            machine="test-machine",
            logical_cpus=8,
            physical_cpus=4,
            affinity_cpus=4,
            cpu_quota_cores=None,
            effective_cpus=4,
            memory_total_bytes=8 * 1024**3,
            memory_available_bytes=6 * 1024**3,
            memory_limit_bytes=None,
            effective_memory_available_bytes=6 * 1024**3,
            constraints=("cpu_affinity",),
        )
        inspector = Mock()
        inspector.inspect.return_value = resources
        self.runner_inspector = Provider(inspector)
        self.runner_policy_planner = Provider(
            RunnerPolicyPlanner(memory_budget_fraction=1)
        )
        transcription_planner = Mock()
        transcription_planner.plan.return_value = transcription_plan()
        self.transcription_planner = Provider(transcription_planner)


def transcription_plan() -> TranscriptionJobPlan:
    source = Path("input.wav").resolve()
    job = Job(JobId("job-1"), source, Path("state/jobs/job-1"), Path("output"))
    artifact = Artifact(
        job.job_id, ArtifactKind.CANONICAL_JSON, job.output_dir / "input.json"
    )
    media = MediaInfo(
        InputIdentity(source, 5, 1, "0" * 64),
        "wav",
        1.25,
        (MediaStream(0, StreamKind.AUDIO, "pcm_s16le", 1.25, 16_000, 1),),
        0,
    )
    resources = RunnerResources(
        platform="TestOS",
        machine="test-machine",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=8 * 1024**3,
        memory_available_bytes=6 * 1024**3,
        memory_limit_bytes=None,
        effective_memory_available_bytes=6 * 1024**3,
        constraints=("cpu_affinity",),
    )
    policy = ExecutionPolicy(
        ProcessingProfile.BALANCED,
        False,
        4,
        4 * 1024**3,
        ModelTier.STANDARD,
    )
    engine = CpuEngineConfiguration(
        "faster-whisper",
        "small",
        "cpu",
        "int8",
        4,
        5,
        None,
        Path("cache/models/faster-whisper/small"),
    )
    return TranscriptionJobPlan(
        job,
        artifact,
        media,
        resources,
        policy,
        engine,
        DecodeConfiguration(DecodeStrategy.DIRECT, "pcm_s16le", 16_000, 1),
        ResourceEstimate(1, 2, 3, 4, 5, True),
        ("paths_are_unreserved",),
    )


def invoke_doctor(status: OverallStatus, *arguments: str):
    container = FakeContainer(report(status))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["doctor", *arguments])
    return result, container


def test_bare_command_shows_help_without_constructing_application():
    with patch("echoflow.cli.AppContainer") as container:
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "doctor" in result.output
    assert "init" in result.output
    assert "runner" in result.output
    assert "transcribe" in result.output
    container.assert_not_called()


def test_healthy_doctor_exits_zero_and_renders_each_check_once():
    result, _ = invoke_doctor(OverallStatus.HEALTHY)
    assert result.exit_code == 0
    assert result.output.count("workspace result") == 1


def test_degraded_exit_code_depends_on_strict_mode():
    ordinary, _ = invoke_doctor(OverallStatus.DEGRADED)
    strict, _ = invoke_doctor(OverallStatus.DEGRADED, "--strict")
    assert ordinary.exit_code == 0
    assert strict.exit_code == 1


def test_unhealthy_doctor_exits_one():
    result, _ = invoke_doctor(OverallStatus.UNHEALTHY)
    assert result.exit_code == 1


def test_json_output_is_parseable_and_unstyled():
    result, _ = invoke_doctor(OverallStatus.HEALTHY, "--json")
    payload = json.loads(result.stdout)
    assert payload["status"] == "healthy"
    assert "\x1b[" not in result.stdout


def test_workspace_option_reaches_config_as_a_path(tmp_path):
    result, container = invoke_doctor(
        OverallStatus.HEALTHY, "--workspace", str(tmp_path)
    )
    assert result.exit_code == 0
    assert tmp_path == container.config().STATE_DIR


def test_init_is_human_readable_and_initializes_once():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "directories initialized" in result.output
    assert "output_dir" in result.output
    container.workspace_service().initialize.assert_called_once_with()


def test_init_json_is_parseable_and_output_override_reaches_config(tmp_path):
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["init", "--output-dir", str(tmp_path), "--json"])
    payload = json.loads(result.stdout)
    assert set(payload) == {"state_dir", "cache_dir", "model_dir", "output_dir"}
    assert tmp_path == container.config().OUTPUT_DIR
    assert "\x1b[" not in result.stdout


def test_init_contract_failure_uses_typed_public_exit_code():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    container.workspace_service().initialize.side_effect = UnsafePathError(
        "Output overlaps private state"
    )
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["init"])
    assert result.exit_code == 2
    assert "Output overlaps private state" in result.stderr


def test_init_internal_failure_hides_private_details():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    container.workspace_service().initialize.side_effect = RuntimeError(
        "private detail"
    )
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["init"])
    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "private detail" not in result.output


def test_unknown_option_uses_click_usage_exit_code():
    result = runner.invoke(app, ["doctor", "--does-not-exist"])
    assert result.exit_code == 2


def test_unexpected_internal_failure_uses_reserved_internal_exit_code():
    with patch("echoflow.cli.AppContainer", side_effect=RuntimeError("private detail")):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "private detail" not in result.output


def test_runner_json_reports_effective_limits_and_screening_semantics():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["runner", "--profile", "screening", "--json"])
    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["resources"]["effective_cpus"] == 4
    assert payload["policy"]["profile"] == "screening"
    assert payload["policy"]["provisional"] is True
    assert payload["policy"]["recommended_model_tier"] == "compact"


def test_runner_human_output_explains_policy():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["runner"])
    assert result.exit_code == 0
    assert "EchoFlow runner policy" in result.output
    assert "balanced" in result.output
    assert "cpu_affinity" in result.output


def test_explicit_configuration_file_is_loaded_only_when_selected(tmp_path):
    config_file = tmp_path / "research.env"
    config_file.write_text("ECHOFLOW_PROCESSING_PROFILE=screening\n")
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["--config", str(config_file), "runner", "--json"])
    assert result.exit_code == 0
    assert container.config().PROCESSING_PROFILE is ProcessingProfile.SCREENING
    assert json.loads(result.stdout)["policy"]["profile"] == "screening"


def test_transcribe_requires_explicit_dry_run_without_constructing_application():
    with patch("echoflow.cli.AppContainer") as container:
        result = runner.invoke(app, ["transcribe", "recording.wav"])
    assert result.exit_code == 2
    assert "use --dry-run" in result.stderr
    container.assert_not_called()


def test_transcribe_dry_run_json_emits_complete_machine_readable_plan():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app, ["transcribe", "recording.wav", "--dry-run", "--json"]
        )
    document = json.loads(result.stdout)
    assert result.exit_code == 0
    assert document["schema_version"] == 1
    assert document["dry_run"] is True
    assert document["paths_reserved"] is False
    assert document["media"]["streams"][0]["codec"] == "pcm_s16le"
    assert document["engine"]["model"] == "small"
    assert document["resources"]["heuristic"] is True
    assert "\x1b[" not in result.stdout


def test_transcribe_dry_run_human_output_explains_unreserved_plan():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "recording.wav", "--dry-run"])
    assert result.exit_code == 0
    assert "EchoFlow transcription dry run" in result.output
    assert "faster-whisper" in result.output
    assert "Paths reserved" in result.output
    assert "false" in result.output


def test_transcribe_overrides_profile_and_output_for_planner(tmp_path):
    container = FakeContainer(report(OverallStatus.HEALTHY))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "recording.wav",
                "--dry-run",
                "--profile",
                "screening",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
    assert result.exit_code == 0
    container.transcription_planner().plan.assert_called_once_with(
        Path("recording.wav"),
        output_dir=(tmp_path / "output").resolve(),
        profile=ProcessingProfile.SCREENING,
    )


def test_transcribe_typed_failure_uses_public_message_and_exit_code():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    container.transcription_planner().plan.side_effect = UnsupportedMediaError(
        "Input contains no audio stream"
    )
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "video.mp4", "--dry-run"])
    assert result.exit_code == 2
    assert result.stderr.strip() == "Input contains no audio stream"


def test_transcribe_missing_input_does_not_echo_sensitive_path(tmp_path):
    container = FakeContainer(report(OverallStatus.HEALTHY))
    sensitive = tmp_path / "participant-001-interview.wav"
    container.transcription_planner().plan.side_effect = InvalidInputError(sensitive)
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", str(sensitive), "--dry-run"])
    assert result.exit_code == 2
    assert result.stderr.strip() == "Input is not a readable local file"
    assert "participant-001" not in result.output


def test_transcribe_internal_failure_hides_private_detail():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    container.transcription_planner().plan.side_effect = RuntimeError(
        "private participant path"
    )
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "audio.wav", "--dry-run"])
    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "private participant path" not in result.output
