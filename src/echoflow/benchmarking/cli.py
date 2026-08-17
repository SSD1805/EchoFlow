import json
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.benchmarking.models import (
    BenchmarkRunError,
    BenchmarkRunResult,
)
from echoflow.core.config import AppConfig
from echoflow.core.errors import EchoFlowError
from echoflow.core.measurements import ExecutionObserver
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
)
from echoflow.workspace.models import JobId

app = typer.Typer(
    name="echoflow-benchmark",
    help="Run privacy-minimized empirical EchoFlow calibration.",
)


def _container(config_file: Path | None) -> AppContainer:
    container = AppContainer()
    if config_file is not None:
        container.config.override(AppConfig.load(config_file))
    return container


def _plan(
    container: AppContainer,
    input_path: Path,
    *,
    output_dir: Path | None,
    profile: ProcessingProfile | None,
    strategy: str | None,
    resume: str | None,
) -> TranscriptionJobPlan:
    planner = container.transcription_planner()
    if resume is not None:
        if profile is not None or strategy is not None:
            raise typer.BadParameter(
                "--resume restores the original profile and strategy; "
                "do not override them"
            )
        return planner.plan_resume(
            input_path,
            output_dir=output_dir,
            job_id=JobId(resume),
        )

    selected_profile = profile or container.config().PROCESSING_PROFILE
    if strategy is None:
        return planner.plan(
            input_path,
            output_dir=output_dir,
            profile=selected_profile,
        )
    return planner.plan(
        input_path,
        output_dir=output_dir,
        profile=selected_profile,
        strategy_id=strategy,
    )


def _execute(
    container: AppContainer,
    plan: TranscriptionJobPlan,
    observer: ExecutionObserver,
    *,
    resume: bool,
) -> TranscriptionExecutionResult:
    executor = container.transcription_executor(observer=observer)
    if resume:
        return executor.execute(plan, resume=True)
    return executor.execute(plan)


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units[:-1]:
        if amount < 1024:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"


def _render(result: BenchmarkRunResult) -> None:
    report = result.report
    table = Table(title="EchoFlow empirical benchmark")
    table.add_column("Measurement")
    table.add_column("Value")
    rows = (
        ("Status", report.status.value),
        ("Job ID", report.job_id),
        ("Real-time factor", f"{report.real_time_factor:.3f}x"),
        ("Total wall time", f"{report.total_wall_seconds:.3f} seconds"),
        ("Planning", f"{report.planning_wall_seconds:.3f} seconds"),
        ("Execution", f"{report.execution_wall_seconds:.3f} seconds"),
        ("Peak process-tree RSS", _format_bytes(report.process_tree.peak_rss_bytes)),
        ("Peak sampled CPU", f"{report.process_tree.peak_cpu_percent:.1f}%"),
        ("Benchmark report", str(result.report_path)),
        ("Transcript artifact", str(result.transcription.artifact.path)),
    )
    for name, value in rows:
        table.add_row(name, value)
    Console().print(table)


@app.command()
def benchmark(
    input_path: Annotated[
        Path,
        typer.Argument(
            metavar="INPUT",
            help="Local audio-bearing recording to benchmark with real transcription.",
        ),
    ],
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
    output_dir: Annotated[
        Path | None,
        typer.Option(
            help="Consumer directory for transcript and benchmark artifacts.",
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
        typer.Option(help="Explicit safe strategy ID from `echoflow strategies`."),
    ] = None,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            metavar="JOB_ID",
            help="Measure a validated resume of an interrupted job.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the benchmark result as JSON."),
    ] = False,
) -> None:
    """Run a local transcription and persist privacy-minimized empirical metrics."""
    try:
        container = _container(config_file)
        planning_started = perf_counter()
        plan = _plan(
            container,
            input_path,
            output_dir=output_dir,
            profile=profile,
            strategy=strategy,
            resume=resume,
        )
        planning_wall_seconds = perf_counter() - planning_started
        if resume is None:
            typer.echo(f"EchoFlow job ID: {plan.job.job_id.value}", err=True)
        result = container.benchmark_runner().run(
            plan,
            execute=lambda observer: _execute(
                container,
                plan,
                observer,
                resume=resume is not None,
            ),
            resume=resume is not None,
            planning_wall_seconds=planning_wall_seconds,
        )
    except typer.BadParameter:
        raise
    except BenchmarkRunError as exc:
        typer.echo(f"EchoFlow benchmark report: {exc.report_path}", err=True)
        if isinstance(exc.cause, KeyboardInterrupt):
            typer.echo(
                "EchoFlow benchmark interrupted; completed checkpoints were retained.",
                err=True,
            )
            raise typer.Exit(code=130) from None
        if isinstance(exc.cause, EchoFlowError):
            typer.echo(exc.cause.public_message, err=True)
            raise typer.Exit(code=exc.cause.exit_code) from None
        typer.echo(
            f"EchoFlow benchmark failed internally ({type(exc.cause).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValidationError:
        typer.echo("Invalid EchoFlow configuration", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(
            f"EchoFlow benchmark failed internally ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=3) from None

    if json_output:
        typer.echo(json.dumps(result.to_dict(), sort_keys=True))
    else:
        _render(result)


def main() -> None:
    app()