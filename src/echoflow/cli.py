import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.app.job_runner import TranscriptionJobRunner
from echoflow.cli_jobs import register_job_commands
from echoflow.cli_models import register_model_commands
from echoflow.cli_progress import RichTranscriptionProgress
from echoflow.core.config import AppConfig
from echoflow.core.errors import EchoFlowError
from echoflow.core.health_check import HealthReport
from echoflow.core.measurements import ExecutionObserver
from echoflow.media.models import StreamKind
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.transcription.export import TranscriptExportFormat, TranscriptExportResult
from echoflow.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
)
from echoflow.transcription.speaker_models import SpeakerDiarizationRequest
from echoflow.workspace.models import JobId, WorkspacePaths

app = typer.Typer(
    name="echoflow",
    help="Local-first audio processing and transcription.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@dataclass(frozen=True, slots=True)
class CliOptions:
    config_file: Path | None = None


@app.callback()
def root(
    context: typer.Context,
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Explicit EchoFlow dotenv configuration file.",
        ),
    ] = None,
) -> None:
    """EchoFlow command-line interface."""
    context.obj = CliOptions(config_file=config_file)
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


def _container(context: typer.Context) -> AppContainer:
    container = AppContainer()
    options = context.ensure_object(CliOptions)
    if options.config_file is not None:
        container.config.override(AppConfig.load(options.config_file))
    return container


register_job_commands(app, _container)
register_model_commands(app, _container)


def _render_report(report: HealthReport, console: Console) -> None:
    table = Table(title=f"EchoFlow doctor: {report.status.value}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Result")
    for result in report.checks:
        table.add_row(result.check_id, result.status.value, result.summary)
    console.print(table)


def _render_paths(paths: WorkspacePaths, console: Console) -> None:
    table = Table(title="EchoFlow directories initialized")
    table.add_column("Purpose")
    table.add_column("Path")
    for purpose, path in paths.to_dict().items():
        table.add_row(purpose, path)
    console.print(table)


def _render_runner(
    resources: RunnerResources, policy: ExecutionPolicy, console: Console
) -> None:
    table = Table(title="EchoFlow runner policy")
    table.add_column("Setting")
    table.add_column("Value")
    rows = {
        "Platform": f"{resources.platform} {resources.machine}",
        "Effective CPUs": str(resources.effective_cpus),
        "Effective memory": str(resources.effective_memory_available_bytes),
        "Profile": policy.profile.value,
        "Provisional": str(policy.provisional).lower(),
        "CPU threads": str(policy.cpu_threads),
        "Memory budget": str(policy.memory_budget_bytes),
        "Model tier": policy.recommended_model_tier.value,
        "Constraints": ", ".join(policy.constraints) or "none",
    }
    for setting, value in rows.items():
        table.add_row(setting, value)
    console.print(table)


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units[:-1]:
        if amount < 1024:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"


def _render_strategies(
    assessments: tuple[dict[str, object], ...], console: Console
) -> None:
    table = Table(title="EchoFlow local transcription strategies")
    table.add_column("Strategy")
    table.add_column("Target")
    table.add_column("Safe")
    table.add_column("Resources")
    table.add_column("Status")
    for assessment in assessments:
        strategy = cast("dict[str, object]", assessment["strategy"])
        reasons = cast("list[str]", assessment["rejection_reasons"])
        status = "recommended" if assessment["recommended"] else ""
        if reasons:
            status = ", ".join(reasons)
        device = str(strategy.get("device", "cpu"))
        compute_type = str(strategy.get("compute_type", "int8"))
        device_memory = int(
            cast("int", strategy.get("estimated_peak_device_memory_bytes", 0))
        )
        peak_vram = _format_bytes(device_memory) if device_memory else "n/a"
        resources = (
            f"RAM {_format_bytes(int(cast('int', strategy['estimated_peak_memory_bytes'])))}; "
            f"VRAM {peak_vram}; "
            f"cache {_format_bytes(int(cast('int', strategy['model_cache_bytes'])))}"
        )
        table.add_row(
            str(strategy["strategy_id"]),
            f"{device}/{compute_type}",
            str(assessment["feasible"]).lower(),
            resources,
            status,
        )
    console.print(table)


def _render_transcription_plan(plan: TranscriptionJobPlan, console: Console) -> None:
    audio = plan.media.primary_audio_stream
    audio_streams = ", ".join(
        str(stream.index)
        for stream in plan.media.streams
        if stream.kind is StreamKind.AUDIO
    )
    enhancement = plan.enhancement.provider if plan.enhancement.enabled else "off"
    table = Table(title="EchoFlow transcription dry run")
    table.add_column("Setting")
    table.add_column("Planned value")
    rows = (
        ("Job ID", plan.job.job_id.value),
        ("Input", str(plan.job.input_path)),
        ("SHA-256", plan.media.input.sha256),
        ("Container", plan.media.container_format),
        ("Duration", f"{plan.media.duration_seconds:.3f} seconds"),
        ("Streams", str(len(plan.media.streams))),
        ("Available audio streams", audio_streams),
        ("Selected audio stream", str(audio.index)),
        ("Primary codec", audio.codec),
        ("Workspace", str(plan.job.workspace_dir)),
        ("Canonical output", str(plan.artifact.path)),
        ("Paths reserved", str(plan.paths_reserved).lower()),
        ("Profile", plan.policy.profile.value),
        ("Provisional", str(plan.policy.provisional).lower()),
        ("Engine", plan.engine.engine),
        ("Model", plan.engine.model),
        ("Model revision", plan.engine.model_revision),
        ("Execution target", f"{plan.engine.device} / {plan.engine.compute_type}"),
        ("CPU threads", str(plan.engine.cpu_threads)),
        ("Decode", plan.decoder.strategy.value),
        ("Noise suppression", enhancement),
        ("Estimated disk", _format_bytes(plan.resources.total_disk_bytes)),
        (
            "Estimated peak memory",
            _format_bytes(plan.resources.estimated_peak_memory_bytes),
        ),
        ("Fits memory budget", str(plan.resources.fits_memory_budget).lower()),
        ("Warnings", ", ".join(plan.warnings) or "none"),
    )
    for setting, value in rows:
        table.add_row(setting, value)
    console.print(table)


def _render_transcription_result(
    result: TranscriptionExecutionResult,
    exports: TranscriptExportResult,
    console: Console,
) -> None:
    transcript = result.transcript
    enhancement = transcript.enhancement
    table = Table(title="EchoFlow transcription complete")
    table.add_column("Setting")
    table.add_column("Value")
    rows = [
        ("Job ID", result.job.job_id.value),
        ("Canonical output", str(result.artifact.path)),
        ("Profile", transcript.profile.value),
        ("Provisional", str(transcript.provisional).lower()),
        ("Engine", f"{transcript.engine.name} {transcript.engine.package_version}"),
        ("Model", transcript.engine.model),
        ("Model revision", transcript.engine.model_revision),
        (
            "Execution target",
            f"{transcript.engine.device} / {transcript.engine.compute_type}",
        ),
        ("CPU threads", str(transcript.engine.cpu_threads)),
        ("Decode", transcript.decode_strategy.value),
        (
            "Noise suppression",
            "off" if enhancement is None else enhancement.provider,
        ),
        ("Audio stream", str(transcript.source.audio_stream_index)),
        ("Detected language", transcript.detected_language or "unknown"),
        ("Segments", str(len(transcript.segments))),
        ("Speakers", str(len({turn.speaker_ref for turn in transcript.speaker_turns}))),
    ]
    rows.extend(
        (f"{artifact.kind.value.upper()} export", str(artifact.path))
        for artifact in exports.artifacts
    )
    for setting, value in rows:
        table.add_row(setting, value)
    console.print(table)


@app.command("init")
def initialize(
    context: typer.Context,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            file_okay=False,
            help="Directory for user-visible EchoFlow artifacts.",
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable directory paths.")
    ] = False,
) -> None:
    """Initialize private application directories and the public output folder."""
    try:
        container = _container(context)
        if output_dir is not None:
            current = container.config()
            container.config.override(
                current.model_copy(update={"OUTPUT_DIR": output_dir})
            )
        paths = container.workspace_service().initialize()
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow initialization failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(paths.to_dict(), sort_keys=True))
    else:
        _render_paths(paths, Console())


@app.command()
def doctor(
    context: typer.Context,
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace", file_okay=False, help="Private state directory to diagnose."
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit a machine-readable health report.")
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat warnings as a failed diagnostic."),
    ] = False,
) -> None:
    """Check local state, disk, FFmpeg, and system resources."""
    try:
        container = _container(context)
        if workspace is not None:
            current = container.config()
            container.config.override(
                current.model_copy(update={"STATE_DIR": workspace})
            )
        report = container.health_check().run()
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow doctor failed internally ({type(exc).__name__})", err=True
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(report.to_dict(), sort_keys=True))
    else:
        _render_report(report, Console())
    if report.exit_code(strict=strict):
        raise typer.Exit(code=1)


@app.command("runner")
def inspect_runner(
    context: typer.Context,
    profile: Annotated[
        ProcessingProfile | None,
        typer.Option(help="Override the configured processing profile."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit a machine-readable runner policy.")
    ] = False,
) -> None:
    """Inspect effective CPU/memory limits and derive a processing policy."""
    try:
        container = _container(context)
        config = container.config()
        selected_profile = profile or config.PROCESSING_PROFILE
        resources = container.runner_inspector().inspect()
        policy = container.runner_policy_planner().plan(resources, selected_profile)
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow runner inspection failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(
            json.dumps(
                {"resources": resources.to_dict(), "policy": policy.to_dict()},
                sort_keys=True,
            )
        )
    else:
        _render_runner(resources, policy, Console())


@app.command("strategies")
def strategies(
    context: typer.Context,
    profile: Annotated[
        ProcessingProfile | None,
        typer.Option(help="Profile used to rank currently safe strategies."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable strategy assessments.")
    ] = False,
) -> None:
    """Show local transcription strategies and their current resource requirements."""
    try:
        container = _container(context)
        selected_profile = profile or container.config().PROCESSING_PROFILE
        assessments = container.transcription_planner().assess_strategies(
            profile=selected_profile
        )
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow strategy inspection failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(list(assessments), sort_keys=True))
    else:
        _render_strategies(assessments, Console())


def _validate_resume_options(
    *,
    dry_run: bool,
    resume: str | None,
    profile: ProcessingProfile | None,
    strategy: str | None,
    audio_stream: int | None,
    enhance: bool,
    export_formats: list[TranscriptExportFormat] | None,
    diarize: bool,
    allow_diarization_model_download: bool,
    speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> None:
    if dry_run and resume is not None:
        raise typer.BadParameter("--resume cannot be combined with --dry-run")
    if resume is not None and (
        profile is not None
        or strategy is not None
        or audio_stream is not None
        or enhance
    ):
        raise typer.BadParameter(
            "--resume restores the original profile, strategy, audio stream, and "
            "enhancement contract; do not override them"
        )
    if dry_run and export_formats:
        raise typer.BadParameter("--export cannot be combined with --dry-run")
    if dry_run and diarize:
        raise typer.BadParameter("--diarize cannot be combined with --dry-run")
    if allow_diarization_model_download and not diarize:
        raise typer.BadParameter(
            "--allow-diarization-model-download requires --diarize"
        )
    if not diarize and any(
        value is not None for value in (speakers, min_speakers, max_speakers)
    ):
        raise typer.BadParameter("speaker-count options require --diarize")


def _diarization_request(
    *,
    enabled: bool,
    speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> SpeakerDiarizationRequest | None:
    if not enabled:
        return None
    try:
        return SpeakerDiarizationRequest(
            num_speakers=speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _plan_transcription(
    container: AppContainer,
    input_path: Path,
    *,
    output_dir: Path | None,
    profile: ProcessingProfile | None,
    strategy: str | None,
    audio_stream: int | None,
    enhance: bool,
    resume: str | None,
) -> TranscriptionJobPlan:
    planner = container.transcription_planner()
    if resume is not None:
        return planner.plan_resume(
            input_path,
            output_dir=output_dir,
            job_id=JobId(resume),
        )
    selected_profile = profile or container.config().PROCESSING_PROFILE
    return planner.plan(
        input_path,
        output_dir=output_dir,
        profile=selected_profile,
        strategy_id=strategy,
        audio_stream_index=audio_stream,
        enhance=enhance,
    )


def _execute_transcription(
    container: AppContainer,
    plan: TranscriptionJobPlan,
    *,
    resume: bool,
    diarization_request: SpeakerDiarizationRequest | None,
    allow_diarization_model_download: bool,
    observer: ExecutionObserver | None = None,
) -> TranscriptionExecutionResult:
    runner = TranscriptionJobRunner(
        lifecycle_store=container.job_lifecycle_store(),
        executor_factory=lambda execution_observer: container.transcription_executor(
            observer=execution_observer
        ),
    )
    return runner.execute(
        plan,
        resume=resume,
        diarization_request=diarization_request,
        allow_diarization_model_download=allow_diarization_model_download,
        observer=observer,
    )


def _publish_exports(
    container: AppContainer,
    result: TranscriptionExecutionResult,
    formats: list[TranscriptExportFormat] | None,
) -> TranscriptExportResult:
    if not formats:
        return TranscriptExportResult(())
    return container.transcript_exporter().publish(
        result.job,
        result.transcript,
        tuple(formats),
    )


def _render_transcription_command_output(
    plan: TranscriptionJobPlan,
    result: TranscriptionExecutionResult | None,
    exports: TranscriptExportResult,
    *,
    dry_run: bool,
    json_output: bool,
) -> None:
    if dry_run:
        if json_output:
            typer.echo(json.dumps(plan.to_dict(), sort_keys=True))
        else:
            _render_transcription_plan(plan, Console())
        return
    execution_result = cast("TranscriptionExecutionResult", result)
    if json_output:
        document = execution_result.to_dict()
        document["exports"] = exports.to_dict()
        typer.echo(json.dumps(document, sort_keys=True))
    else:
        _render_transcription_result(execution_result, exports, Console())


def _execute_cli_plan(
    container: AppContainer,
    plan: TranscriptionJobPlan,
    *,
    dry_run: bool,
    json_output: bool,
    resume: str | None,
    diarization_request: SpeakerDiarizationRequest | None,
    allow_diarization_model_download: bool,
    export_formats: list[TranscriptExportFormat] | None,
) -> tuple[TranscriptionExecutionResult | None, TranscriptExportResult]:
    if dry_run:
        return None, TranscriptExportResult(())
    if resume is None:
        typer.echo(f"EchoFlow job ID: {plan.job.job_id.value}", err=True)
    if json_output:
        result = _execute_transcription(
            container,
            plan,
            resume=resume is not None,
            diarization_request=diarization_request,
            allow_diarization_model_download=allow_diarization_model_download,
        )
    else:
        with RichTranscriptionProgress() as progress:
            result = _execute_transcription(
                container,
                plan,
                resume=resume is not None,
                diarization_request=diarization_request,
                allow_diarization_model_download=allow_diarization_model_download,
                observer=progress,
            )
    return result, _publish_exports(container, result, export_formats)


def _report_transcription_interrupt(plan: TranscriptionJobPlan | None) -> None:
    typer.echo("", err=True)
    if plan is None:
        typer.echo("EchoFlow interrupted before the job started.", err=True)
        return
    typer.echo(
        "EchoFlow job interrupted. Your completed segments remain private and "
        "checkpointed.",
        err=True,
    )
    typer.echo(
        f"Resume: echoflow transcribe {plan.job.input_path} "
        f"--resume {plan.job.job_id.value}",
        err=True,
    )


@app.command("transcribe")
def transcribe(
    context: typer.Context,
    input_path: Annotated[
        Path,
        typer.Argument(
            metavar="INPUT",
            help="Local audio-bearing recording to transcribe.",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan without creating files or transcribing."),
    ] = False,
    enhance: Annotated[
        bool,
        typer.Option(
            "--enhance",
            help="Apply local deterministic speech noise suppression before ASR.",
        ),
    ] = False,
    diarize: Annotated[
        bool,
        typer.Option(
            "--diarize",
            help="Add anonymous local speaker turns and conservative speaker labels.",
        ),
    ] = False,
    allow_diarization_model_download: Annotated[
        bool,
        typer.Option(
            "--allow-diarization-model-download",
            help="Authorize network acquisition only for the optional diarization model.",
        ),
    ] = False,
    speakers: Annotated[
        int | None,
        typer.Option(
            "--speakers",
            min=1,
            help="Known exact speaker count for diarization.",
        ),
    ] = None,
    min_speakers: Annotated[
        int | None,
        typer.Option("--min-speakers", min=1, help="Minimum expected speakers."),
    ] = None,
    max_speakers: Annotated[
        int | None,
        typer.Option("--max-speakers", min=1, help="Maximum expected speakers."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            help="Consumer directory for transcript artifacts.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    profile: Annotated[
        ProcessingProfile | None,
        typer.Option(help="Override the configured processing profile."),
    ] = None,
    strategy: Annotated[
        str | None,
        typer.Option(
            help="Explicit safe strategy ID from `echoflow strategies`; never silently downgraded."
        ),
    ] = None,
    audio_stream: Annotated[
        int | None,
        typer.Option(
            "--audio-stream",
            metavar="INDEX",
            help="FFmpeg stream index for the audio track to transcribe.",
        ),
    ] = None,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            metavar="JOB_ID",
            help="Resume a compatible interrupted job from private local checkpoints.",
        ),
    ] = None,
    export_formats: Annotated[
        list[TranscriptExportFormat] | None,
        typer.Option(
            "--export",
            help="Derived transcript format to publish; repeat for TXT, SRT, or VTT.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the plan or execution result as JSON."),
    ] = False,
) -> None:
    """Transcribe a local recording, optionally resuming validated private state."""
    plan: TranscriptionJobPlan | None = None
    try:
        _validate_resume_options(
            dry_run=dry_run,
            resume=resume,
            profile=profile,
            strategy=strategy,
            audio_stream=audio_stream,
            enhance=enhance,
            export_formats=export_formats,
            diarize=diarize,
            allow_diarization_model_download=allow_diarization_model_download,
            speakers=speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        speaker_request = _diarization_request(
            enabled=diarize,
            speakers=speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        container = _container(context)
        plan = _plan_transcription(
            container,
            input_path,
            output_dir=output_dir,
            profile=profile,
            strategy=strategy,
            audio_stream=audio_stream,
            enhance=enhance,
            resume=resume,
        )
        result, exports = _execute_cli_plan(
            container,
            plan,
            dry_run=dry_run,
            json_output=json_output,
            resume=resume,
            diarization_request=speaker_request,
            allow_diarization_model_download=allow_diarization_model_download,
            export_formats=export_formats,
        )
    except KeyboardInterrupt:
        _report_transcription_interrupt(plan)
        raise typer.Exit(code=130) from None
    except (typer.BadParameter, typer.Exit):
        raise
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow transcription failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    _render_transcription_command_output(
        plan,
        result,
        exports,
        dry_run=dry_run,
        json_output=json_output,
    )


def main() -> None:
    app()
