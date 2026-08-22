from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress

from scholion.transcription.models import AudioSegmentWindow
from scholion.transcription.segmentation import MaterializedAudioSegment


class OrderedSegmentPrefetcher:
    """Materialize at most one future segment while the caller consumes the current one."""

    def __init__(
        self,
        *,
        materialize: Callable[[AudioSegmentWindow], MaterializedAudioSegment],
        cleanup: Callable[[MaterializedAudioSegment], None],
        prefetch_depth: int,
    ):
        if prefetch_depth not in (0, 1):
            raise ValueError("prefetch_depth must be zero or one")
        self.materialize = materialize
        self.cleanup = cleanup
        self.prefetch_depth = prefetch_depth
        self._executor: ThreadPoolExecutor | None = None
        self._future: Future[MaterializedAudioSegment] | None = None

    def __enter__(self) -> OrderedSegmentPrefetcher:
        if self._executor is not None:
            raise RuntimeError("segment prefetcher is already active")
        if self.prefetch_depth:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="scholion-segment-prefetch",
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self._cleanup_pending()
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    def iterate(
        self, windows: tuple[AudioSegmentWindow, ...]
    ) -> Iterator[MaterializedAudioSegment]:
        if self.prefetch_depth == 0:
            yield from (self.materialize(window) for window in windows)
            return
        if self._executor is None:
            raise RuntimeError("segment prefetcher must be entered before iteration")
        iterator = iter(windows)
        first = next(iterator, None)
        if first is None:
            return
        self._future = self._executor.submit(self.materialize, first)
        while self._future is not None:
            future = self._future
            materialized = future.result()
            self._future = None
            following = next(iterator, None)
            if following is not None:
                self._future = self._executor.submit(self.materialize, following)
            yield materialized

    def _cleanup_pending(self) -> None:
        future = self._future
        self._future = None
        if future is None or future.cancel():
            return
        try:
            materialized = future.result()
        except Exception:
            return
        with suppress(Exception):
            self.cleanup(materialized)
