"""Derived human presentation over canonical anonymous speaker evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import SpeakerLabelStateError
from echoflow.library.index import IndexedDocument, TranscriptIndex
from echoflow.library.speaker_labels import SpeakerLabelStore


class SpeakerPresentationKind(StrEnum):
    """How confidently a derived text span can be presented with speaker evidence."""

    SINGLE = "single-speaker"
    OVERLAP = "overlap"
    MIXED_UNRESOLVED = "mixed-unresolved"
    UNATTRIBUTED = "unattributed"


@dataclass(frozen=True, slots=True)
class PresentedSpeaker:
    """Anonymous evidence ref plus optional human-authored display label."""

    speaker_ref: str
    display_label: str | None = None

    def __post_init__(self) -> None:
        if not self.speaker_ref.strip():
            raise ValueError("speaker_ref cannot be empty")
        if self.display_label is not None and not self.display_label.strip():
            raise ValueError("display_label cannot be empty")

    @property
    def display_name(self) -> str:
        if self.display_label is None:
            return self.speaker_ref
        return f"{self.display_label} ({self.speaker_ref})"

    def to_dict(self) -> dict[str, str | None]:
        return {
            "speaker_ref": self.speaker_ref,
            "display_label": self.display_label,
            "display_name": self.display_name,
        }


@dataclass(frozen=True, slots=True)
class SpeakerPresentationSpan:
    """One source-relative derived text span for speaker-aware reading."""

    document_id: str
    canonical_sha256: str
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speakers: tuple[PresentedSpeaker, ...]
    kind: SpeakerPresentationKind

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.segment_id.strip():
            raise ValueError("presentation identity cannot be empty")
        if len(self.canonical_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.canonical_sha256
        ):
            raise ValueError("canonical_sha256 must be a lowercase 64-character digest")
        if (
            not math.isfinite(self.start_seconds)
            or not math.isfinite(self.end_seconds)
            or self.start_seconds < 0
            or self.end_seconds < self.start_seconds
        ):
            raise ValueError("presentation timestamps must be finite and ordered")
        if not self.text.strip():
            raise ValueError("presentation text cannot be empty")
        refs = tuple(speaker.speaker_ref for speaker in self.speakers)
        if refs != tuple(sorted(set(refs))):
            raise ValueError("presentation speakers must be unique and sorted")
        if self.kind is SpeakerPresentationKind.SINGLE and len(self.speakers) != 1:
            raise ValueError("single-speaker presentation requires exactly one speaker")
        if self.kind is SpeakerPresentationKind.OVERLAP and len(self.speakers) < 2:
            raise ValueError("overlap presentation requires multiple speakers")
        if self.kind is SpeakerPresentationKind.UNATTRIBUTED and self.speakers:
            raise ValueError("unattributed presentation cannot name speakers")

    @property
    def overlap(self) -> bool:
        return self.kind is SpeakerPresentationKind.OVERLAP

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "canonical_sha256": self.canonical_sha256,
            "segment_id": self.segment_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "kind": self.kind.value,
            "overlap": self.overlap,
            "speakers": [speaker.to_dict() for speaker in self.speakers],
        }


class _Word(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_seconds: float
    end_seconds: float
    text: str
    speaker_ref: str | None = None


class _Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_ref: str | None = None
    words: list[_Word] = Field(default_factory=list)


class _Turn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_seconds: float
    end_seconds: float
    speaker_ref: str


class _CanonicalPresentationProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segments: list[_Segment]
    speaker_turns: list[_Turn] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _WordEvidence:
    start_seconds: float
    end_seconds: float
    text: str
    speaker_refs: tuple[str, ...]
    kind: SpeakerPresentationKind


class SpeakerPresentationService:
    """Build readable handoff/overlap spans without changing canonical evidence."""

    def __init__(
        self,
        index: TranscriptIndex,
        label_store: SpeakerLabelStore,
        file_manager: FileManagerFacade,
    ) -> None:
        self.index = index
        self.label_store = label_store
        self.file_manager = file_manager

    def spans(self, document_id: str) -> tuple[SpeakerPresentationSpan, ...]:
        document = self._document(document_id)
        canonical_sha256 = self._require_canonical_hash(document)
        projection = self._load_projection(document, canonical_sha256)
        labels = {
            item.speaker_ref: item.label
            for item in self.label_store.current_labels(document)
        }
        spans: list[SpeakerPresentationSpan] = []
        for segment in projection.segments:
            if segment.words:
                spans.extend(
                    self._word_spans(
                        document,
                        canonical_sha256,
                        segment,
                        projection.speaker_turns,
                        labels,
                    )
                )
            else:
                spans.append(
                    self._segment_span(
                        document,
                        canonical_sha256,
                        segment,
                        projection.speaker_turns,
                        labels,
                    )
                )
        return tuple(spans)

    def _word_spans(
        self,
        document: IndexedDocument,
        canonical_sha256: str,
        segment: _Segment,
        turns: list[_Turn],
        labels: dict[str, str],
    ) -> tuple[SpeakerPresentationSpan, ...]:
        evidence = tuple(self._word_evidence(word, turns) for word in segment.words)
        grouped: list[list[_WordEvidence]] = []
        for word in evidence:
            if (
                grouped
                and grouped[-1][-1].speaker_refs == word.speaker_refs
                and grouped[-1][-1].kind is word.kind
            ):
                grouped[-1].append(word)
            else:
                grouped.append([word])
        return tuple(
            self._build_span(
                document=document,
                canonical_sha256=canonical_sha256,
                segment_id=segment.segment_id,
                start_seconds=group[0].start_seconds,
                end_seconds=group[-1].end_seconds,
                text="".join(item.text for item in group).strip(),
                speaker_refs=group[0].speaker_refs,
                kind=group[0].kind,
                labels=labels,
            )
            for group in grouped
        )

    def _word_evidence(self, word: _Word, turns: list[_Turn]) -> _WordEvidence:
        active = self._active_refs(word.start_seconds, word.end_seconds, turns)
        if len(active) > 1:
            return _WordEvidence(
                word.start_seconds,
                word.end_seconds,
                word.text,
                active,
                SpeakerPresentationKind.OVERLAP,
            )
        if word.speaker_ref is not None and word.speaker_ref.strip():
            return _WordEvidence(
                word.start_seconds,
                word.end_seconds,
                word.text,
                (word.speaker_ref,),
                SpeakerPresentationKind.SINGLE,
            )
        return _WordEvidence(
            word.start_seconds,
            word.end_seconds,
            word.text,
            (),
            SpeakerPresentationKind.UNATTRIBUTED,
        )

    def _segment_span(
        self,
        document: IndexedDocument,
        canonical_sha256: str,
        segment: _Segment,
        turns: list[_Turn],
        labels: dict[str, str],
    ) -> SpeakerPresentationSpan:
        refs: tuple[str, ...]
        kind: SpeakerPresentationKind
        if segment.speaker_ref is not None and segment.speaker_ref.strip():
            refs = (segment.speaker_ref,)
            kind = SpeakerPresentationKind.SINGLE
        else:
            refs = self._active_refs(segment.start_seconds, segment.end_seconds, turns)
            if not refs:
                kind = SpeakerPresentationKind.UNATTRIBUTED
            elif len(refs) == 1:
                # Canonical segment attribution deliberately declined this assignment.
                # Preserve that uncertainty rather than deriving a stronger claim here.
                refs = ()
                kind = SpeakerPresentationKind.UNATTRIBUTED
            elif self._has_simultaneous_overlap(
                segment.start_seconds, segment.end_seconds, turns
            ):
                kind = SpeakerPresentationKind.OVERLAP
            else:
                kind = SpeakerPresentationKind.MIXED_UNRESOLVED
        return self._build_span(
            document=document,
            canonical_sha256=canonical_sha256,
            segment_id=segment.segment_id,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text.strip(),
            speaker_refs=refs,
            kind=kind,
            labels=labels,
        )

    @staticmethod
    def _active_refs(
        start_seconds: float,
        end_seconds: float,
        turns: list[_Turn],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    turn.speaker_ref
                    for turn in turns
                    if min(end_seconds, turn.end_seconds)
                    > max(start_seconds, turn.start_seconds)
                }
            )
        )

    @staticmethod
    def _has_simultaneous_overlap(
        start_seconds: float,
        end_seconds: float,
        turns: list[_Turn],
    ) -> bool:
        relevant = [
            turn
            for turn in turns
            if min(end_seconds, turn.end_seconds)
            > max(start_seconds, turn.start_seconds)
        ]
        for index, first in enumerate(relevant):
            for second in relevant[index + 1 :]:
                if first.speaker_ref == second.speaker_ref:
                    continue
                if min(end_seconds, first.end_seconds, second.end_seconds) > max(
                    start_seconds, first.start_seconds, second.start_seconds
                ):
                    return True
        return False

    @staticmethod
    def _build_span(
        *,
        document: IndexedDocument,
        canonical_sha256: str,
        segment_id: str,
        start_seconds: float,
        end_seconds: float,
        text: str,
        speaker_refs: tuple[str, ...],
        kind: SpeakerPresentationKind,
        labels: dict[str, str],
    ) -> SpeakerPresentationSpan:
        speakers = tuple(
            PresentedSpeaker(speaker_ref=ref, display_label=labels.get(ref))
            for ref in speaker_refs
        )
        return SpeakerPresentationSpan(
            document_id=document.document_id,
            canonical_sha256=canonical_sha256,
            segment_id=segment_id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            text=text,
            speakers=speakers,
            kind=kind,
        )

    def _load_projection(
        self,
        document: IndexedDocument,
        canonical_sha256: str,
    ) -> _CanonicalPresentationProjection:
        try:
            payload = self.file_manager.read_file(Path(document.canonical_path))
            if hashlib.sha256(payload).hexdigest() != canonical_sha256:
                raise SpeakerLabelStateError(
                    "Canonical transcript changed; rebuild the library before reading speaker presentation"
                )
            return _CanonicalPresentationProjection.model_validate(json.loads(payload))
        except SpeakerLabelStateError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise SpeakerLabelStateError(
                "Canonical speaker presentation evidence could not be validated safely",
                cause=exc,
            ) from exc

    def _document(self, document_id: str) -> IndexedDocument:
        document = next(
            (
                item
                for item in self.index.documents()
                if item.document_id == document_id
            ),
            None,
        )
        if document is None:
            raise SpeakerLabelStateError(
                "Transcript is not present in the local library; rebuild the library first"
            )
        return document

    @staticmethod
    def _require_canonical_hash(document: IndexedDocument) -> str:
        if document.canonical_sha256 is None:
            raise SpeakerLabelStateError(
                "Transcript index predates canonical hashing; rebuild the library first"
            )
        return document.canonical_sha256
