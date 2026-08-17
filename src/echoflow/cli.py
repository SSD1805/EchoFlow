from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from dependency_injector import providers
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.config import AppConfig
from echoflow.core.errors import EchoFlowError
from echoflow.media.models import StreamKind
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.export import (
    TranscriptExportFormat,
    TranscriptExportResult,
)
from echoflow.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
)
from echoflow.transcription.speaker_models import SpeakerDiarizationRequest
from echoflow.workspace.models import JobId

app = typer.Typer(no_args_is_help=True)


def _container(context: typer.Context) -> AppContainer:
    container = context.obj
    if not isinstance(container, AppContainer):
        raise RuntimeError("EchoFlow application container is unavailable")
    return container


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def _render_paths(paths, console: Console) -> None:
    table = Table(title="EchoFlow workspace")
    table.add_column("Path")
    table.add_column("Location")
    for name, value in paths.to_dict().items():
        table.add_row(name, value)
    console.print(table)


def _render_health(report, console: Console) -> None:
    table = Table(title="EchoFlow doctor")
    table.add_column("Probe")
    table.add_column("Status")
    table.add_column("Message")
    for result in report.results:
        table.add_row(result.name, result.status.value, result.message)
    console.print(table)


def _render_runner(snapshot, console: Console) -> None:
    table = Table(title="EchoFlow runner")
    table.add_column("Resource")
    table.add_column("Value")
    rows = (
        ("Effective CPUs", str(snapshot.effective_cpu_count)),
        ("Effective memory", _format_bytes(snapshot.effective_memory_bytes)),
        ("Available memory", _format_bytes(snapshot.available_memory_bytes)),
        ("Process memory", _format_bytes(snapshot.process_memory_bytes)),
    )
    for name, value in rows:
        table.add_row(name, value)
    console.print(table)


def _render_strategies(assessments, console: Console) -> None:
    table = Table(title="EchoFlow transcription strategies")
    table.add_column("Strategy")
    table.add_column("Model")
    table.add_column("Fits")
    table.add_column("Estimated peak memory")
    table.add_column("Reason")
    for assessment in assessments:
        strategy = assessment.strategy
        table.add_row(
            strategy.strategy_id,
            strategy.model,
            str(assessment.feasible).lower(),
            _format_bytes(strategy.estimated_peak_memory_bytes),
            assessment.reason,
        )
    console.print(table)


def _render_transcription_plan(plan: TranscriptionJobPlan, console: Console) -> None:
    audio = plan.media.primary_audio_stream
    audio_streams = ", ".join(
        f"{stream.index}:{stream.codec}"
        for stream in plan.media.streams
        if stream.kind is StreamKind.AUDIO
    )
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
        ("CPU configuration", f"{plan.engine.cpu_threads} threads / int8"),
        ("Decode", plan.decoder.strategy.value),
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
        ("Decode", transcript.decode_strategy.value),
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
        bool, typer.Option("--json", help="Emit machine-readable health output.")
    ] = False,
) -> None:
    """Run local health checks without modifying user data."""
    try:
        container = _container(context)
        if workspace is not None:
            current = container.config()
            container.config.override(current.model_copy(update={"STATE_DIR": workspace}))
        report = container.health_check().run()
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow health check failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(report.to_dict(), sort_keys=True))
    else:
        _render_health(report, Console())


@app.command()
def runner(
    context: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable runner resources.")
    ] = False,
) -> None:
    """Inspect the local compute resources visible to EchoFlow."""
    try:
        snapshot = _container(context).runner_inspector().inspect()
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow runner inspection failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(snapshot.to_dict(), sort_keys=True))
    else:
        _render_runner(snapshot, Console())


@app.command()
def strategies(
    context: typer.Context,
    profile: Annotated[
        ProcessingProfile | None,
        typer.Option("--profile", case_sensitive=False, help="Processing intent."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable strategy output.")
    ] = False,
) -> None:
    """Show transcription strategies that fit this machine's current policy."""
    try:
        container = _container(context)
        selected_profile = profile or container.config().PROCESSING_PROFILE
        runner_snapshot = container.runner_inspector().inspect()
        policy = container.runner_policy_planner().plan(runner_snapshot, selected_profile)
        assessments = container.transcription_planner().evaluate_strategies(policy)
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
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
    export_formats: list[TranscriptExportFormat] | None,
    diarize: bool,
    speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> None:
    if dry_run and resume is not None:
        raise typer.BadParameter("--resume cannot be combined with --dry-run")
    if resume is not None and (
        profile is not None or strategy is not None or audio_stream is not None
    ):
        raise typer.BadParameter(
            "--resume restores the original profile, strategy, and audio stream; "
            "do not override them"
        )
    if dry_run and export_formats:
        raise typer.BadParameter("--export cannot be combined with --dry-run")
    if dry_run and diarize:
        raise typer.BadParameter("--diarize cannot be combined with --dry-run")
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
    if strategy is None and audio_stream is None:
        return planner.plan(
            input_path,
            output_dir=output_dir,
            profile=selected_profile,
        )
    if strategy is None:
        return planner.plan(
            input_path,
            output_dir=output_dir,
            profile=selected_profile,
            audio_stream_index=audio_stream,
        )
    if audio_stream is None:
        return planner.plan(
            input_path,
            output_dir=output_dir,
            profile=selected_profile,
            strategy_id=strategy,
        )
    return planner.plan(
        input_path,
        output_dir=output_dir,
        profile=selected_profile,
        strategy_id=strategy,
        audio_stream_index=audio_stream,
    )


def _execute_transcription(
    container: AppContainer,
    plan: TranscriptionJobPlan,
    *,
    allow_model_download: bool,
    resume: bool,
    diarization_request: SpeakerDiarizationRequest | None,
) -> TranscriptionExecutionResult:
    executor = container.transcription_executor()
    if diarization_request is None:
        if resume:
            return executor.execute(
                plan,
                allow_model_download=allow_model_download,
                resume=True,
            )
        return executor.execute(
            plan,
            allow_model_download=allow_model_download,
        )
    if resume:
        return executor.execute(
            plan,
            allow_model_download=allow_model_download,
            resume=True,
            diarization_request=diarization_request,
        )
    return executor.execute(
        plan,
        allow_model_download=allow_model_download,
        diarization_request=diarization_request,
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


@app.command()
def transcribe(
    context: typer.Context,
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", file_okay=False, help="Public artifact directory."),
    ] = None,
    profile: Annotated[
        ProcessingProfile | None,
        typer.Option("--profile", case_sensitive=False, help="Processing intent."),
    ] = None,
    strategy: Annotated[
        str | None,
        typer.Option("--strategy", help="Explicit transcription strategy ID."),
    ] = None,
    audio_stream: Annotated[
        int | None,
        typer.Option("--audio-stream", min=0, help="Explicit audio stream index."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Plan without executing transcription.")
    ] = False,
    allow_model_download: Annotated[
        bool,
        typer.Option(
            "--allow-model-download",
            help="Allow required local model files to be downloaded.",
        ),
    ] = False,
    export_formats: Annotated[
        list[TranscriptExportFormat] | None,
        typer.Option(
            "--export",
            case_sensitive=False,
            help="Publish a derived transcript view. Repeat for multiple formats.",
        ),
    ] = None,
    diarize: Annotated[
        bool,
        typer.Option(
            "--diarize",
            help="Add anonymous local speaker turns and conservative speaker labels.",
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
    resume: Annotated[
        str | None,
        typer.Option("--resume", help="Resume a previously interrupted EchoFlow job."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable execution output.")
    ] = False,
) -> None:
    """Plan or execute one local transcription job."""
    try:
        _validate_resume_options(
            dry_run=dry_run,
            resume=resume,
            profile=profile,
            strategy=strategy,
            audio_stream=audio_stream,
            export_formats=export_formats,
            diarize=diarize,
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
            resume=resume,
        )
        if dry_run:
            if json_output:
                typer.echo(json.dumps(plan.to_dict(), sort_keys=True))
            else:
                _render_transcription_plan(plan, Console())
            return
        result = _execute_transcription(
            container,
            plan,
            allow_model_download=allow_model_download,
            resume=resume is not None,
            diarization_request=speaker_request,
        )
        exports = _publish_exports(container, result, export_formats)
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except typer.BadParameter:
        raise
    except Exception as exc:
        typer.echo(
            f"EchoFlow transcription failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "result": result.to_dict(),
                    "exports": exports.to_dict(),
                },
                sort_keys=True,
            )
        )
    else:
        _render_transcription_result(result, exports, Console())


def main() -> None:
    container = AppContainer()
    app(obj=container)


if __name__ == "__main__":
    main()
