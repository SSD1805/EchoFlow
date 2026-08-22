"""Durable user-authored display labels for anonymous transcript speakers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.library.errors import SpeakerLabelStateError
from scholion.library.index import IndexedDocument

_STATE_SCHEMA_VERSION = 1
_MAX_LABEL_LENGTH = 200


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("canonical_sha256 must be a lowercase 64-character digest")


@dataclass(frozen=True, slots=True)
class SpeakerDisplayLabel:
    """One human-authored name bound to one anonymous speaker evidence generation."""

    document_id: str
    canonical_sha256: str
    speaker_ref: str
    label: str

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        _validate_sha256(self.canonical_sha256)
        if not self.speaker_ref.strip():
            raise ValueError("speaker_ref cannot be empty")
        normalized = self.label.strip()
        if not normalized:
            raise ValueError("speaker display label cannot be empty")
        if len(normalized) > _MAX_LABEL_LENGTH:
            raise ValueError(
                f"speaker display label cannot exceed {_MAX_LABEL_LENGTH} characters"
            )
        if any(character in "\r\n\x00" for character in normalized):
            raise ValueError("speaker display label cannot contain line breaks or NUL")
        object.__setattr__(self, "label", normalized)

    def to_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "canonical_sha256": self.canonical_sha256,
            "speaker_ref": self.speaker_ref,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class SpeakerLabelView:
    """A stored label plus whether it still matches the current canonical evidence."""

    binding: SpeakerDisplayLabel
    current: bool


class _StoredLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    canonical_sha256: str
    speaker_ref: str
    label: str


class _StoredState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    labels: list[_StoredLabel]


class _CanonicalWordSpeaker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker_ref: str | None = None


class _CanonicalSegmentSpeaker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker_ref: str | None = None
    words: list[_CanonicalWordSpeaker] = Field(default_factory=list)


class _CanonicalSpeakerProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segments: list[_CanonicalSegmentSpeaker]


def canonical_speaker_refs(
    document: IndexedDocument,
    file_manager: FileManagerFacade,
) -> tuple[str, ...]:
    """Return anonymous refs from the exact canonical generation in the index.

    Mixed-speaker ASR segments may have no segment-level label while their aligned
    words do, so both evidence levels are inspected. The canonical hash is checked
    before accepting a human label to avoid binding a name to stale speaker numbering.
    """
    canonical_sha256 = SpeakerLabelStore._require_canonical_hash(document)
    try:
        payload = file_manager.read_file(Path(document.canonical_path))
        if hashlib.sha256(payload).hexdigest() != canonical_sha256:
            raise SpeakerLabelStateError(
                "Canonical transcript changed; rebuild the library before editing speaker labels"
            )
        projection = _CanonicalSpeakerProjection.model_validate(json.loads(payload))
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
            "Canonical speaker evidence could not be validated safely",
            cause=exc,
        ) from exc

    refs: set[str] = set()
    for segment in projection.segments:
        if segment.speaker_ref is not None and segment.speaker_ref.strip():
            refs.add(segment.speaker_ref)
        refs.update(
            word.speaker_ref
            for word in segment.words
            if word.speaker_ref is not None and word.speaker_ref.strip()
        )
    return tuple(sorted(refs))


class SpeakerLabelStore:
    """Own non-rebuildable speaker display labels separately from search indexes."""

    def __init__(self, path: Path, file_manager: FileManagerFacade) -> None:
        self.path = path.expanduser().resolve(strict=False)
        self.file_manager = file_manager

    def set_label(
        self,
        document: IndexedDocument,
        *,
        speaker_ref: str,
        label: str,
    ) -> SpeakerDisplayLabel:
        canonical_sha256 = self._require_canonical_hash(document)
        binding = SpeakerDisplayLabel(
            document_id=document.document_id,
            canonical_sha256=canonical_sha256,
            speaker_ref=speaker_ref,
            label=label,
        )
        state = self._load()
        keyed = {
            (item.document_id, item.canonical_sha256, item.speaker_ref): item
            for item in state
        }
        keyed[(binding.document_id, binding.canonical_sha256, binding.speaker_ref)] = (
            binding
        )
        self._save(tuple(sorted(keyed.values(), key=self._sort_key)))
        return binding

    def remove_label(self, document: IndexedDocument, *, speaker_ref: str) -> bool:
        canonical_sha256 = self._require_canonical_hash(document)
        state = self._load()
        retained = tuple(
            item
            for item in state
            if not (
                item.document_id == document.document_id
                and item.canonical_sha256 == canonical_sha256
                and item.speaker_ref == speaker_ref
            )
        )
        if len(retained) == len(state):
            return False
        self._save(retained)
        return True

    def current_labels(
        self, document: IndexedDocument
    ) -> tuple[SpeakerDisplayLabel, ...]:
        canonical_sha256 = self._require_canonical_hash(document)
        return tuple(
            item
            for item in self._load()
            if item.document_id == document.document_id
            and item.canonical_sha256 == canonical_sha256
        )

    def views(self, document: IndexedDocument) -> tuple[SpeakerLabelView, ...]:
        canonical_sha256 = self._require_canonical_hash(document)
        return tuple(
            SpeakerLabelView(
                binding=item,
                current=item.canonical_sha256 == canonical_sha256,
            )
            for item in self._load()
            if item.document_id == document.document_id
        )

    def resolve(
        self,
        *,
        document_id: str,
        canonical_sha256: str | None,
        speaker_ref: str,
    ) -> str | None:
        if canonical_sha256 is None:
            return None
        for item in self._load():
            if (
                item.document_id == document_id
                and item.canonical_sha256 == canonical_sha256
                and item.speaker_ref == speaker_ref
            ):
                return item.label
        return None

    def _load(self) -> tuple[SpeakerDisplayLabel, ...]:
        if not self.file_manager.file_exists(self.path):
            return ()
        try:
            payload = json.loads(self.file_manager.read_file(self.path))
            state = _StoredState.model_validate(payload)
            if state.schema_version != _STATE_SCHEMA_VERSION:
                raise SpeakerLabelStateError(
                    "Speaker label state was written by an unsupported Scholion schema"
                )
            labels = tuple(
                SpeakerDisplayLabel(
                    document_id=item.document_id,
                    canonical_sha256=item.canonical_sha256,
                    speaker_ref=item.speaker_ref,
                    label=item.label,
                )
                for item in state.labels
            )
            keys = tuple(
                (item.document_id, item.canonical_sha256, item.speaker_ref)
                for item in labels
            )
            if len(keys) != len(set(keys)):
                raise SpeakerLabelStateError(
                    "Speaker label state contains duplicate evidence bindings"
                )
            return tuple(sorted(labels, key=self._sort_key))
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
                "Speaker label state could not be validated safely",
                cause=exc,
            ) from exc

    def _save(self, labels: tuple[SpeakerDisplayLabel, ...]) -> None:
        self.file_manager.ensure_directory_exists(self.path.parent, private=True)
        document = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "labels": [item.to_dict() for item in labels],
        }
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        self.file_manager.save_file(payload, self.path, private=True)

    @staticmethod
    def _require_canonical_hash(document: IndexedDocument) -> str:
        if document.canonical_sha256 is None:
            raise SpeakerLabelStateError(
                "Transcript index predates canonical hashing; rebuild the library first"
            )
        return document.canonical_sha256

    @staticmethod
    def _sort_key(item: SpeakerDisplayLabel) -> tuple[str, str, str]:
        return (item.document_id, item.canonical_sha256, item.speaker_ref)
