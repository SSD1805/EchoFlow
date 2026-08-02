import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.core.health_check import HealthReport
from echoflow.workspace.models import WorkspacePaths

app = typer.Typer(
    name="echoflow",
    help="Local-first audio processing and transcription.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def root(context: typer.Context) -> None:
    """EchoFlow command-line interface."""
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


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


@app.command("init")
def initialize(
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
        container = AppContainer()
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
        container = AppContainer()
        if workspace is not None:
            current = container.config()
            container.config.override(
                current.model_copy(update={"STATE_DIR": workspace})
            )
        report = container.health_check().run()
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


def main() -> None:
    app()
