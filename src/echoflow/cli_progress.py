from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

_STAGE_LABELS = {
    "admission.initial": "Checking resources",
    "media.verify": "Verifying recording",
    "admission.storage": "Checking storage",
    "workspace.claim": "Preparing private job",
    "decode": "Preparing audio",
    "segmentation.plan": "Planning segments",
    "checkpoint.prepare": "Checking saved progress",
    "admission.pre_model": "Rechecking resources",
    "engine.open": "Loading speech model",
    "segment.materialize": "Preparing segment",
    "segment.transcribe": "Transcribing",
    "checkpoint.write": "Saving progress",
    "transcript.assemble": "Assembling transcript",
    "speaker.diarize": "Finding anonymous speakers",
    "transcript.canonicalize": "Finalizing transcript",
    "artifact.write": "Writing transcript",
    "checkpoint.cleanup": "Cleaning checkpoints",
    "decode.cleanup": "Cleaning temporary audio",
}


class RichTranscriptionProgress:
    """Presentation-only observer for interactive CLI execution."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True)
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
            disable=not self.console.is_terminal,
        )
        self.task_id = self.progress.add_task("Starting", total=None)

    def __enter__(self) -> RichTranscriptionProgress:
        self.progress.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.progress.stop()

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        label = _STAGE_LABELS.get(name)
        if label is not None:
            self.progress.update(self.task_id, description=label)
        yield

    def record_value(self, name: str, value: int | float) -> None:
        if name == "segments.total":
            self.progress.update(self.task_id, total=int(value))
        elif name == "segments.completed":
            self.progress.update(
                self.task_id,
                completed=int(value),
                description="Transcribing",
            )
