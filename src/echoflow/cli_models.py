from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.model_management.models import ManagedModelManifest, ModelInventoryItem
from echoflow.runner.models import ProcessingProfile

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units[:-1]:
        if amount < 1024:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"


def _render_inventory(
    items: tuple[ModelInventoryItem, ...], console: Console
) -> None:
    table = Table(title="EchoFlow managed models")
    table.add_column("Model")
    table.add_column("Engine")
    table.add_column("Installed")
    table.add_column("Revision")
    table.add_column("Size")
    table.add_column("Repository")
    for item in items:
        manifest = item.manifest
        table.add_row(
            item.spec.model_id,
            item.spec.engine,
            str(item.installed).lower(),
            "-" if manifest is None else manifest.resolved_revision,
            (
                _format_bytes(item.spec.estimated_cache_bytes)
                if manifest is None
                else _format_bytes(manifest.size_bytes)
            ),
            item.spec.repository_id,
        )
    console.print(table)


def _list_models(
    context: typer.Context,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        items = container_factory(_root_context(context)).model_manager().inventory()
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if json_output:
        typer.echo(json.dumps([item.to_dict() for item in items], sort_keys=True))
        return
    _render_inventory(items, Console())


def _install_model(
    context: typer.Context,
    model_id: str,
    *,
    revision: str | None,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        manifest = container_factory(_root_context(context)).model_manager().install(
            model_id, revision=revision
        )
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="MODEL") from exc
    if json_output:
        typer.echo(json.dumps(manifest.to_dict(), sort_keys=True))
        return
    _render_manifest("Model installed", manifest, Console())


def _remove_model(
    context: typer.Context,
    model_id: str,
    *,
    yes: bool,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        container = container_factory(_root_context(context))
        manager = container.model_manager()
        if not manager.is_installed(model_id):
            raise typer.BadParameter("model is not managed by EchoFlow", param_hint="MODEL")
        if not yes and not typer.confirm(
            f"Remove EchoFlow's managed {model_id} model revision from local storage?"
        ):
            raise typer.Abort()
        manifest = manager.remove(model_id)
    except (typer.Abort, typer.BadParameter):
        raise
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="MODEL") from exc
    if json_output:
        typer.echo(json.dumps({"removed": manifest.to_dict()}, sort_keys=True))
        return
    _render_manifest("Model removed", manifest, Console())


def _recommend_model(
    context: typer.Context,
    *,
    profile: ProcessingProfile | None,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        container = container_factory(_root_context(context))
        selected_profile = profile or container.config().PROCESSING_PROFILE
        assessments = container.transcription_planner().assess_strategies(
            profile=selected_profile
        )
        recommended = next(
            assessment for assessment in assessments if assessment["recommended"]
        )
        strategy = cast("dict[str, object]", recommended["strategy"])
        model_id = str(strategy["model"])
        installed = container.model_manager().is_installed(model_id)
    except EchoFlowError as exc:
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    document = {
        "profile": selected_profile.value,
        "model": model_id,
        "installed": installed,
        "strategy": strategy,
    }
    if json_output:
        typer.echo(json.dumps(document, sort_keys=True))
        return
    table = Table(title="EchoFlow model recommendation")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Profile", selected_profile.value)
    table.add_row("Model", model_id)
    table.add_row("Installed", str(installed).lower())
    table.add_row(
        "Execution target", f"{strategy['device']} / {strategy['compute_type']}"
    )
    if not installed:
        table.add_row("Install", f"echoflow models install {model_id}")
    Console().print(table)


def _render_manifest(
    title: str, manifest: ManagedModelManifest, console: Console
) -> None:
    table = Table(title=title)
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Model", manifest.model_id)
    table.add_row("Repository", manifest.repository_id)
    table.add_row("Requested revision", manifest.requested_revision or "default")
    table.add_row("Resolved revision", manifest.resolved_revision)
    table.add_row("Verification", manifest.verification)
    table.add_row("Size", _format_bytes(manifest.size_bytes))
    console.print(table)


def register_model_commands(
    app: typer.Typer, container_factory: ContainerFactory
) -> None:
    models_app = typer.Typer(
        help="Inspect, recommend, install, and remove private local models.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @models_app.callback()
    def models_root(
        context: typer.Context,
        json_output: bool = typer.Option(
            False, "--json", help="Emit machine-readable model inventory."
        ),
    ) -> None:
        if context.invoked_subcommand is None:
            _list_models(
                context,
                json_output=json_output,
                container_factory=container_factory,
            )

    @models_app.command("install")
    def install_model(
        context: typer.Context,
        model_id: str = typer.Argument(..., metavar="MODEL"),
        revision: str | None = typer.Option(
            None,
            "--revision",
            help="Optional provider revision to resolve and record explicitly.",
        ),
        json_output: bool = typer.Option(
            False, "--json", help="Emit the installed model manifest as JSON."
        ),
    ) -> None:
        _install_model(
            context,
            model_id,
            revision=revision,
            json_output=json_output,
            container_factory=container_factory,
        )

    @models_app.command("remove")
    def remove_model(
        context: typer.Context,
        model_id: str = typer.Argument(..., metavar="MODEL"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
        json_output: bool = typer.Option(
            False, "--json", help="Emit the removed model manifest as JSON."
        ),
    ) -> None:
        _remove_model(
            context,
            model_id,
            yes=yes,
            json_output=json_output,
            container_factory=container_factory,
        )

    @models_app.command("recommend")
    def recommend_model(
        context: typer.Context,
        profile: ProcessingProfile | None = typer.Option(
            None, help="Profile used to choose a safe local model strategy."
        ),
        json_output: bool = typer.Option(
            False, "--json", help="Emit the recommendation as JSON."
        ),
    ) -> None:
        _recommend_model(
            context,
            profile=profile,
            json_output=json_output,
            container_factory=container_factory,
        )

    app.add_typer(models_app, name="models")
