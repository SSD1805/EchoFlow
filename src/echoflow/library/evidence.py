"""Resolve ranked transcript passages back to verified canonical evidence coordinates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import EvidenceNavigationError
from echoflow.library.retrieval import SearchPassage, SearchResponse
from echoflow.library.text import lexical_tokens

_MAX_CANONICAL_BYTES = 256 * 1024 * 1024
_MAX_CONTEXT_SEGMENTS = 10


class _CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha256: str


class _CanonicalWord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_seconds: float
    end_seconds: float
    text: str
    speaker_ref: str | None = None


class _CanonicalSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_ref: str | None = None
    words: list[_CanonicalWord] = Field(default_factory=list)


class _CanonicalTranscript(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int
    job_id: str
    source: _CanonicalSource
    segments: list[_CanonicalSegment]


@dataclass(frozen=True, slots=True)
class EvidenceWord:
    """One canonical word coordinate used by a derived research view."""

    segment_id: str
    word_index: int
    start_seconds: float
    end_seconds: float
    text: str
    speaker_ref: str | None
    highlighted: bool = False

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id cannot be empty")
        if self.word_index < 0:
            raise ValueError("word_index cannot be negative")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("word timestamps must be ordered and non-negative")
        if not self.text.strip():
            raise ValueError("word text cannot be empty")


@dataclass(frozen=True, slots=True)
class EvidenceContextSegment:
    """One canonical segment included in a result or its requested context."""

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_refs: tuple[str, ...]
    words: tuple[EvidenceWord, ...]
    is_result_segment: bool
    lexical_match: bool

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id cannot be empty")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("segment timestamps must be ordered and non-negative")
        if not self.text.strip():
            raise ValueError("segment text cannot be empty")


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    """Verified canonical coordinates for one ranked search passage."""

    document_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_path: str
    source_path: str | None
    result_segment_ids: tuple[str, ...]
    start_seconds: float
    end_seconds: float
    seek_seconds: float
    result_speaker_refs: tuple[str, ...]
    matched_words: tuple[EvidenceWord, ...]
    context_segments: tuple[EvidenceContextSegment, ...]

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.result_segment_ids:
            raise ValueError("evidence location requires at least one result segment")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("evidence timestamps must be ordered and non-negative")
        if not self.start_seconds <= self.seek_seconds <= self.end_seconds:
            raise ValueError("seek coordinate must remain inside result evidence")


class EvidenceLocator:
    """Verify canonical custody, expand context, and resolve justified word highlights."""

    def __init__(self, file_manager: FileManagerFacade) -> None:
        self.file_manager = file_manager

    def locate_response(
        self,
        response: SearchResponse,
        *,
        context_segments: int = 0,
    ) -> tuple[EvidenceLocation, ...]:
        if context_segments < 0 or context_segments > _MAX_CONTEXT_SEGMENTS:
            raise ValueError(
                f"context_segments must be between 0 and {_MAX_CONTEXT_SEGMENTS}"
            )
        cache: dict[tuple[str, str], _CanonicalTranscript] = {}
        return tuple(
            self._locate(
                passage,
                response=response,
                context_segments=context_segments,
                cache=cache,
            )
            for passage in response.results
        )

    def _locate(
        self,
        passage: SearchPassage,
        *,
        response: SearchResponse,
        context_segments: int,
        cache: dict[tuple[str, str], _CanonicalTranscript],
    ) -> EvidenceLocation:
        canonical_sha256, canonical = self._canonical_for_passage(passage, cache)
        result_indices = self._result_indices(passage, canonical)
        context, matched_words = self._context_for_passage(
            passage,
            canonical=canonical,
            result_indices=result_indices,
            response=response,
            context_segments=context_segments,
        )
        result_segments = tuple(canonical.segments[index] for index in result_indices)
        self._validate_result_timing(passage, result_segments)
        result_speakers = self._result_speakers(passage, result_segments)
        seek_seconds = (
            matched_words[0].start_seconds if matched_words else passage.start_seconds
        )

        return EvidenceLocation(
            document_id=passage.document_id,
            source_sha256=passage.source_sha256,
            canonical_sha256=canonical_sha256,
            canonical_path=passage.canonical_path,
            source_path=passage.source_path,
            result_segment_ids=passage.segment_ids,
            start_seconds=passage.start_seconds,
            end_seconds=passage.end_seconds,
            seek_seconds=seek_seconds,
            result_speaker_refs=result_speakers,
            matched_words=matched_words,
            context_segments=context,
        )

    def _canonical_for_passage(
        self,
        passage: SearchPassage,
        cache: dict[tuple[str, str], _CanonicalTranscript],
    ) -> tuple[str, _CanonicalTranscript]:
        canonical_sha256 = passage.canonical_sha256
        if canonical_sha256 is None:
            raise EvidenceNavigationError(
                "Transcript index predates canonical hashing; rebuild the library before navigating evidence"
            )
        cache_key = (passage.canonical_path, canonical_sha256)
        canonical = cache.get(cache_key)
        if canonical is None:
            canonical = self._load_canonical(passage, canonical_sha256)
            cache[cache_key] = canonical
        return canonical_sha256, canonical

    @staticmethod
    def _result_indices(
        passage: SearchPassage,
        canonical: _CanonicalTranscript,
    ) -> tuple[int, ...]:
        by_id = {
            segment.segment_id: index
            for index, segment in enumerate(canonical.segments)
        }
        try:
            result_indices = tuple(by_id[item] for item in passage.segment_ids)
        except KeyError as exc:
            raise EvidenceNavigationError(
                "Search result references canonical evidence that no longer exists"
            ) from exc
        if not result_indices:
            raise EvidenceNavigationError(
                "Search result has no canonical evidence segments"
            )
        return result_indices

    def _context_for_passage(
        self,
        passage: SearchPassage,
        *,
        canonical: _CanonicalTranscript,
        result_indices: tuple[int, ...],
        response: SearchResponse,
        context_segments: int,
    ) -> tuple[tuple[EvidenceContextSegment, ...], tuple[EvidenceWord, ...]]:
        first_result = min(result_indices)
        last_result = max(result_indices)
        context_start = max(0, first_result - context_segments)
        context_end = min(len(canonical.segments), last_result + context_segments + 1)
        result_ids = set(passage.segment_ids)
        lexical_ids = set(passage.matched_segment_ids)
        query_tokens = lexical_tokens(response.query.text)
        context: list[EvidenceContextSegment] = []
        matched_words: list[EvidenceWord] = []

        for segment in canonical.segments[context_start:context_end]:
            rendered, highlighted = self._context_segment(
                segment,
                result_ids=result_ids,
                lexical_ids=lexical_ids,
                query_tokens=query_tokens,
                phrase=response.query.phrase,
            )
            context.append(rendered)
            matched_words.extend(highlighted)
        return tuple(context), tuple(matched_words)

    def _context_segment(
        self,
        segment: _CanonicalSegment,
        *,
        result_ids: set[str],
        lexical_ids: set[str],
        query_tokens: tuple[str, ...],
        phrase: bool,
    ) -> tuple[EvidenceContextSegment, tuple[EvidenceWord, ...]]:
        should_highlight = segment.segment_id in lexical_ids
        highlighted_indices = (
            self._highlighted_word_indices(
                segment.words,
                query_tokens=query_tokens,
                phrase=phrase,
            )
            if should_highlight
            else set()
        )
        words = tuple(
            EvidenceWord(
                segment_id=segment.segment_id,
                word_index=index,
                start_seconds=word.start_seconds,
                end_seconds=word.end_seconds,
                text=word.text,
                speaker_ref=word.speaker_ref,
                highlighted=index in highlighted_indices,
            )
            for index, word in enumerate(segment.words)
        )
        highlighted = tuple(word for word in words if word.highlighted)
        return (
            EvidenceContextSegment(
                segment_id=segment.segment_id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                speaker_refs=self._segment_speakers(segment),
                words=words,
                is_result_segment=segment.segment_id in result_ids,
                lexical_match=should_highlight,
            ),
            highlighted,
        )

    @staticmethod
    def _validate_result_timing(
        passage: SearchPassage,
        result_segments: tuple[_CanonicalSegment, ...],
    ) -> None:
        result_start = min(segment.start_seconds for segment in result_segments)
        result_end = max(segment.end_seconds for segment in result_segments)
        if (
            passage.start_seconds < result_start - 1e-6
            or passage.end_seconds > result_end + 1e-6
        ):
            raise EvidenceNavigationError(
                "Search result timing does not fit its canonical evidence segments"
            )

    def _result_speakers(
        self,
        passage: SearchPassage,
        result_segments: tuple[_CanonicalSegment, ...],
    ) -> tuple[str, ...]:
        result_speakers = tuple(
            sorted(
                {
                    ref
                    for segment in result_segments
                    for ref in self._segment_speakers(segment)
                }
            )
        )
        return result_speakers or passage.speaker_refs

    def _load_canonical(
        self,
        passage: SearchPassage,
        canonical_sha256: str,
    ) -> _CanonicalTranscript:
        try:
            payload = self.file_manager.read_file(Path(passage.canonical_path))
            if len(payload) > _MAX_CANONICAL_BYTES:
                raise EvidenceNavigationError(
                    "Canonical transcript is too large to navigate safely"
                )
            if hashlib.sha256(payload).hexdigest() != canonical_sha256:
                raise EvidenceNavigationError(
                    "Canonical transcript changed; rebuild the library before navigating evidence"
                )
            canonical = _CanonicalTranscript.model_validate(json.loads(payload))
            if canonical.schema_version != 1:
                raise EvidenceNavigationError(
                    "Canonical transcript schema is unsupported by this EchoFlow build"
                )
            if canonical.job_id != passage.document_id:
                raise EvidenceNavigationError(
                    "Canonical transcript identity does not match the search result"
                )
            if canonical.source.sha256 != passage.source_sha256:
                raise EvidenceNavigationError(
                    "Canonical source identity does not match the search result"
                )
            return canonical
        except EvidenceNavigationError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise EvidenceNavigationError(
                "Canonical evidence could not be validated for navigation",
                cause=exc,
            ) from exc

    @staticmethod
    def _segment_speakers(segment: _CanonicalSegment) -> tuple[str, ...]:
        refs = {
            word.speaker_ref
            for word in segment.words
            if word.speaker_ref is not None and word.speaker_ref.strip()
        }
        if segment.speaker_ref is not None and segment.speaker_ref.strip():
            refs.add(segment.speaker_ref)
        return tuple(sorted(refs))

    @staticmethod
    def _highlighted_word_indices(
        words: list[_CanonicalWord],
        *,
        query_tokens: tuple[str, ...],
        phrase: bool,
    ) -> set[int]:
        if not words or not query_tokens:
            return set()
        flattened: list[tuple[str, int]] = []
        for index, word in enumerate(words):
            flattened.extend((token, index) for token in lexical_tokens(word.text))
        if not flattened:
            return set()
        if not phrase:
            requested = set(query_tokens)
            return {word_index for token, word_index in flattened if token in requested}

        tokens = tuple(token for token, _ in flattened)
        width = len(query_tokens)
        highlighted: set[int] = set()
        for offset in range(0, len(tokens) - width + 1):
            if tokens[offset : offset + width] != query_tokens:
                continue
            highlighted.update(
                word_index for _, word_index in flattened[offset : offset + width]
            )
        return highlighted
