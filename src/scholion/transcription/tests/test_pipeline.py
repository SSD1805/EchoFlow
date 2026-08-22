from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from scholion.transcription.models import AudioSegmentWindow
from scholion.transcription.pipeline import OrderedSegmentPrefetcher
from scholion.transcription.segmentation import MaterializedAudioSegment


def windows(count=3):
    return tuple(
        AudioSegmentWindow(index, index * 10, (index + 1) * 10, 10)
        for index in range(count)
    )


def materialized(window):
    return MaterializedAudioSegment(window, Path.cwd() / f"{window.segment_id}.wav")


@pytest.mark.parametrize("depth", [-1, 2, 100])
def test_prefetch_depth_is_deliberately_bounded_to_zero_or_one(depth):
    with pytest.raises(ValueError, match="^prefetch_depth must be zero or one$"):
        OrderedSegmentPrefetcher(
            materialize=materialized,
            cleanup=lambda _segment: None,
            prefetch_depth=depth,
        )


def test_depth_zero_is_strictly_sequential_and_needs_no_worker_pool():
    calls = []

    def make(window):
        calls.append(window.index)
        return materialized(window)

    pipeline = OrderedSegmentPrefetcher(
        materialize=make,
        cleanup=lambda _segment: None,
        prefetch_depth=0,
    )
    iterator = pipeline.iterate(windows(2))

    first = next(iterator)
    assert first.window.index == 0
    assert calls == [0]

    second = next(iterator)
    assert second.window.index == 1
    assert calls == [0, 1]

    with pytest.raises(StopIteration):
        next(iterator)


def test_depth_one_prefetches_next_before_current_is_yielded():
    second_started = Event()
    permit_second = Event()

    def make(window):
        if window.index == 1:
            second_started.set()
            assert permit_second.wait(timeout=1)
        return materialized(window)

    pipeline = OrderedSegmentPrefetcher(
        materialize=make,
        cleanup=lambda _segment: None,
        prefetch_depth=1,
    )
    with pipeline:
        iterator = pipeline.iterate(windows(2))
        first = next(iterator)
        assert first.window.index == 0
        assert second_started.wait(timeout=1)
        permit_second.set()
        second = next(iterator)
        assert second.window.index == 1


def test_depth_one_requires_active_context_before_iteration():
    pipeline = OrderedSegmentPrefetcher(
        materialize=materialized,
        cleanup=lambda _segment: None,
        prefetch_depth=1,
    )
    with pytest.raises(
        RuntimeError, match="^segment prefetcher must be entered before iteration$"
    ):
        next(pipeline.iterate(windows(1)))


def test_context_cannot_be_entered_twice():
    pipeline = OrderedSegmentPrefetcher(
        materialize=materialized,
        cleanup=lambda _segment: None,
        prefetch_depth=1,
    )
    with (
        pipeline,
        pytest.raises(RuntimeError, match="^segment prefetcher is already active$"),
    ):
        pipeline.__enter__()


def test_empty_window_set_materializes_nothing():
    make = Mock()
    with OrderedSegmentPrefetcher(
        materialize=make,
        cleanup=Mock(),
        prefetch_depth=1,
    ) as pipeline:
        assert tuple(pipeline.iterate(())) == ()
    make.assert_not_called()


def test_materialization_failure_propagates_without_inventing_cleanup():
    cleanup = Mock()

    def fail(_window):
        raise OSError("materialization failed")

    with (
        OrderedSegmentPrefetcher(
            materialize=fail,
            cleanup=cleanup,
            prefetch_depth=1,
        ) as pipeline,
        pytest.raises(OSError, match="^materialization failed$"),
    ):
        next(pipeline.iterate(windows(1)))
    cleanup.assert_not_called()


def test_consumer_failure_cleans_only_prefetched_unconsumed_segment():
    cleanup = Mock()
    second_started = Event()
    permit_second = Event()

    def make(window):
        if window.index == 1:
            second_started.set()
            assert permit_second.wait(timeout=1)
        return materialized(window)

    first = None
    with (
        pytest.raises(RuntimeError, match="^consumer failed$"),
        OrderedSegmentPrefetcher(
            materialize=make,
            cleanup=cleanup,
            prefetch_depth=1,
        ) as pipeline,
    ):
        iterator = pipeline.iterate(windows(2))
        first = next(iterator)
        assert second_started.wait(timeout=1)
        permit_second.set()
        raise RuntimeError("consumer failed")

    assert first is not None
    assert cleanup.call_count == 1
    assert cleanup.call_args.args[0].window.index == 1
    assert cleanup.call_args.args[0] != first


def test_pending_cleanup_failure_never_masks_primary_consumer_error():
    def cleanup(_segment):
        raise OSError("cleanup failed")

    with (
        pytest.raises(RuntimeError, match="^consumer failed$"),
        OrderedSegmentPrefetcher(
            materialize=materialized,
            cleanup=cleanup,
            prefetch_depth=1,
        ) as pipeline,
    ):
        iterator = pipeline.iterate(windows(2))
        next(iterator)
        raise RuntimeError("consumer failed")
