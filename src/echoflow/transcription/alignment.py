"""Word-level timestamp evidence layered onto recognized transcript segments."""

from __future__ import annotations

import math
from dataclasses import dataclass

from echoflow.transcription.models import RecognizedSegment

_WORD_SEGMENT_TOLERANCE_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class AlignedWord:
    """One engine-produced word interval relative to its containing audio timeline."""

    start_seconds: float
    end_seconds: float
    text: str
    probability: float | None = None
    speaker_ref: str | None = None

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.start_seconds)
            or not math.isfinite(self.end_seconds)
            or self.start_seconds < 0
            or self.end_seconds < self.start_seconds
        ):
            raise ValueError("word timestamps must be finite and ordered")
        if not self.text.strip():
            raise ValueError("word text cannot be empty")
        if self.probability is not None and not (
            math.isfinite(self.probability) and 0 <= self.probability <= 1
        ):
            raise ValueError("word probability must be between 0 and 1")
        if self.speaker_ref is not None and not self.speaker_ref.strip():
            raise ValueError("word speaker_ref cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "probability": self.probability,
            "speaker_ref": self.speaker_ref,
        }


@dataclass(frozen=True, slots=True)
class AlignedRecognizedSegment(RecognizedSegment):
    """Recognized text carrying optional engine-produced word timing evidence."""

    words: tuple[AlignedWord, ...] = ()

    def __post_init__(self) -> None:
        RecognizedSegment.__post_init__(self)
        self._validate_words()

    def _validate_words(self) -> None:
        previous_end = self.start_seconds
        for word in self.words:
            if (
                word.start_seconds
                < self.start_seconds - _WORD_SEGMENT_TOLERANCE_SECONDS
            ):
                raise ValueError("word timestamp starts before its segment")
            if word.end_seconds > self.end_seconds + _WORD_SEGMENT_TOLERANCE_SECONDS:
                raise ValueError("word timestamp ends after its segment")
            if (
                word.start_seconds
                < previous_end - _WORD_SEGMENT_TOLERANCE_SECONDS
            ):
                raise ValueError("word timestamps must be ordered and non-overlapping")
            previous_end = max(previous_end, word.end_seconds)

        if self.speaker_ref is None or not self.words:
            return
        word_speakers = tuple(word.speaker_ref for word in self.words)
        if any(speaker is None for speaker in word_speakers) or set(word_speakers) != {
            self.speaker_ref
        }:
            raise ValueError(
                "segment speaker_ref requires uniformly attributed aligned words"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            **RecognizedSegment.to_dict(self),
            "words": [word.to_dict() for word in self.words],
        }


def aligned_words(segment: RecognizedSegment) -> tuple[AlignedWord, ...]:
    """Return word evidence without making every consumer alignment-aware."""
    if isinstance(segment, AlignedRecognizedSegment):
        return segment.words
    return ()
