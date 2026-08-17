from __future__ import annotations

import json
from collections.abc import Callable

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.workspace.lifecycle import JobLifecycleRecord, JobStatus
from echoflow.workspace.models import JobId

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    while context.parent is not None:
        context = context.parent
    return context


def _progress_text(record: JobLifecycleRecord) -> str:
    if record.total_segments is None:
        return "not started"
    return f"{record.completed_segments}/{record.total_segments}"


def _record_document(
    container: AppContainer, record: JobLifecycleRecord
) -> dict[str, object]:
    document = record.to_dict()
    document["resumable"] = container.job_lifecycle_store().is_resumable(record.job_id)
    return document


def _render_jobs(
    container: AppContainer,
    records: tuple[JobLifecycleRecord, ...],
    console: Console,
) -> None:
    table = Table(title="EchoFlow jobs")
    table.add_column("Job ID")
    table.add_column("Status")
    table.add_column("Progress")
    table.add_column("Recording")
    table.add_column("Resumable")
    table.add_column("Updated")
    for record in records:
        table.add_row(
            record.job_id.value,
            record.status.value,
            _progress_text(record),
            record.input_path.name,
            str(container.job_lifecycle_store().is_resumable(record.job_id)).lower(),
            record.updated_at,
        )
    console.print(table)


def _render_job(
    container: AppContainer,
    record: JobLifecycleRecord,
    console: Console,
) -> None:
    resumable = container.job_lifecycle_store().is_resumable(record.job_id)
    table = Table(title=f"EchoFlow job {record.job_id.value}")
    table.add_column("Setting")
    table.add_column("Value")
    rows = [
        ("Status", record.status.value),
        ("Progress", _progress_text(record)),
        ("Resumable", str(resumable).lower()),
        ("Input", str(record.input_path)),
        ("Output directory", str(record.output_dir)),
        ("Started", record.started_at),
        ("Updated", record.updated_at),
        ("Error code", record.error_code or "none"),
        (
            "Canonical artifact",
            "none" if record.artifact_path is None else str(record.artifact_path),
        ),
    ]
    if resumable:
        rows.append(
            (
                "Resume",
                f"echoflow transcribe {record.input_path} --resume {record.job_id.value}",
            )
        )
    for setting, value in rows:
        table.add_row(setting, value)
    console.print(table)


def register_job_commands(app: typer.Typer, container_factory: ContainerFactory) -> None:
    jobs_app = typer.Typer(
        help="Inspect and clean up private local transcription jobs.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @jobs_app.callback()
    def jobs_root(
        context: typer.Context,
        json_output: bool = typer.Option(
            False, "--json", help="Emit machine-readable lifecycle records."
        ),
    ) -> None:
        if context.invoked_subcommand is not None:
            return
        try:
            container = container_factory(_root_context(context))
            records = container.job_lifecycle_store().list_records()
        except EchoFlowError as exc:
            typer.echo(exc.public_message, err=True)
            raise typer.Exit(code=exc.exit_code) from None
        except Exception as exc:
            typer.echo(
                f"EchoFlow job inspection failed internally ({type(exc).__name__})",
                err=True,
            )
            raise typer.Exit(code=3) from None
        if json_output:
            typer.echo(
                json.dumps(
                    [_record_document(container, record) for record in records],
                    sort_keys=True,
                )
            )
        else:
            _render_jobs(container, records, Console())

    @jobs_app.command("show")
    def show_job(
        context: typer.Context,
        job_id: str = typer.Argument(..., metavar="JOB_ID"),
        json_output: bool = typer.Option(
            False, "--json", help="Emit the lifecycle record as JSON."
        ),
    ) -> None:
        try:
            container = container_factory(_root_context(context))
            record = container.job_lifecycle_store().get(JobId(job_id))
        except EchoFlowError as exc:
            typer.echo(exc.public_message, err=True)
            raise typer.Exit(code=exc.exit_code) from None
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="JOB_ID") from exc
        if json_output:
            typer.echo(json.dumps(_record_document(container, record), sort_keys=True))
        else:
            _render_job(container, record, Console())

    @jobs_app.command("discard")
    def discard_job(
        context: typer.Context,
        job_id: str = typer.Argument(..., metavar="JOB_ID"),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Discard private state without an interactive confirmation.",
        ),
    ) -> None:
        try:
            container = container_factory(_root_context(context))
            selected = JobId(job_id)
            record = container.job_lifecycle_store().get(selected)
            if record.status is JobStatus.RUNNING:
                raise typer.BadParameter("a running job cannot be discarded")
            if not yes:
                confirmed = typer.confirm(
                    "Discard this job's private checkpoints and lifecycle state? "
                    "Published transcript files will remain."
                )
                if not confirmed:
                    raise typer.Abort()
            container.job_lifecycle_store().discard(selected)
        except typer.Abort:
            raise
        except typer.BadParameter:
            raise
        except EchoFlowError as exc:
            typer.echo(exc.public_message, err=True)
            raise typer.Exit(code=exc.exit_code) from None
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="JOB_ID") from exc
        typer.echo(f"Discarded private EchoFlow job {job_id}")

    app.add_typer(jobs_app, name="jobs")
