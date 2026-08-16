import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.config import AppConfig
from echoflow.core.errors import EchoFlowError
from echoflow.core.health_check import HealthReport
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
)
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
    table.add_column("Model")
    table.add_column("Safe now")
    table.add_column("Peak memory")
    table.add_column("Model cache")
    table.add_column("Recommendation")
    for assessment in assessments:
        strategy = cast("dict[str, object]", assessment["strategy"])
        reasons = cast("list[str]", assessment["rejection_reasons"])
        recommendation = "recommended" if assessment["recommended"] else ""
        if reasons:
            recommendation = ", ".join(reasons)
        table.add_row(
            str(strategy["strategy_id"]),
            str(strategy["model"]),
            str(assessment["feasible"]).lower(),
            _format_bytes(int(cast("int", strategy["estimated_peak_memory_bytes"]))),
            _format_bytes(int(cast("int", strategy["model_cache_bytes"]))),
            recommendation,
        )
    console.print(table)


def _render_transcription_plan(plan: TranscriptionJobPlan, console: Console) -> None:
    audio = plan.media.primary_audio_stream
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
    result: TranscriptionExecutionResult, console: Console
) -> None:
    transcript = result.transcript
    table = Table(title="EchoFlow transcription complete")
    table.add_column("Setting")
    table.add_column("Value")
    rows = (
        ("Job ID", result.job.job_id.value),
        ("Canonical output", str(result.artifact.path)),
        ("Profile", transcript.profile.value),
        ("Provisional", str(transcript.provisional).lower()),
        ("Engine", f"{transcript.engine.name} {transcript.engine.package_version}"),
        ("Model", transcript.engine.model),
        ("Decode", transcript.decode_strategy.value),
        ("Detected language", transcript.detected_language or "unknown"),
        ("Segments", str(len(transcript.segments))),
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
    """Show local transcription strategies and their current memory requirements."""

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
    allow_model_download: Annotated[
        bool,
        typer.Option(
            "--allow-model-download",
            help="Authorize network access to obtain the selected model if absent.",
        ),
    ] = False,
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
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            metavar="JOB_ID",
            help="Resume a compatible interrupted job from private local checkpoints.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the plan or execution result as JSON."),
    ] = False,
) -> None:
    """Transcribe a local recording, optionally resuming validated private state."""
    try:
        if dry_run and resume is not None:
            raise typer.BadParameter("--resume cannot be combined with --dry-run")
        container = _container(context)
        selected_profile = profile or container.config().PROCESSING_PROFILE
        resume_job_id = None if resume is None else JobId(resume)
        plan = container.transcription_planner().plan(
            input_path,
            output_dir=output_dir,
            profile=selected_profile,
            strategy_id=strategy,
            job_id=resume_job_id,
        )
        result = None
        if not dry_run:
            result = container.transcription_executor().execute(
                plan,
                allow_model_download=allow_model_download,
                resume=resume_job_id is not None,
            )
    except typer.BadParameter:
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

    if dry_run and json_output:
        typer.echo(json.dumps(plan.to_dict(), sort_keys=True))
    elif dry_run:
        _render_transcription_plan(plan, Console())
    elif json_output:
        execution_result = cast("TranscriptionExecutionResult", result)
        typer.echo(json.dumps(execution_result.to_dict(), sort_keys=True))
    else:
        _render_transcription_result(
            cast("TranscriptionExecutionResult", result), Console()
        )
