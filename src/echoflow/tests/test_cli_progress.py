from contextlib import nullcontext
from io import StringIO

from rich.console import Console

from echoflow.cli_progress import RichTranscriptionProgress


def test_rich_progress_tracks_stage_total_and_completion():
    console = Console(file=StringIO(), force_terminal=False)
    progress = RichTranscriptionProgress(console)

    with progress:
        with progress.span("engine.open"):
            pass
        progress.record_value("segments.total", 4)
        progress.record_value("segments.completed", 2)
        progress.record_value("unrelated", 99)
        task = progress.progress.tasks[0]
        assert task.total == 4
        assert task.completed == 2
        assert task.description == "Transcribing"


def test_unknown_progress_stage_is_a_noop():
    console = Console(file=StringIO(), force_terminal=False)
    progress = RichTranscriptionProgress(console)
    before = progress.progress.tasks[0].description

    context = progress.span("future.stage")

    assert hasattr(context, "__enter__")
    with context:
        assert nullcontext() is not None
    assert progress.progress.tasks[0].description == before
