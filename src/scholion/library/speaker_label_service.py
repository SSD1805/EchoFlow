"""Application service for human-readable names over anonymous speaker evidence."""

from __future__ import annotations

from dataclasses import dataclass

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.library.errors import SpeakerLabelStateError
from scholion.library.index import IndexedDocument, TranscriptIndex
from scholion.library.speaker_labels import (
    SpeakerDisplayLabel,
    SpeakerLabelStore,
    SpeakerLabelView,
    canonical_speaker_refs,
)


@dataclass(frozen=True, slots=True)
class SpeakerRosterEntry:
    """One current anonymous speaker plus an optional user-authored display name."""

    speaker_ref: str
    display_label: str | None

    @property
    def display_name(self) -> str:
        if self.display_label is None:
            return self.speaker_ref
        return f"{self.display_label} ({self.speaker_ref})"


class SpeakerLabelService:
    """Keep user naming separate from diarization and rebuildable search state."""

    def __init__(
        self,
        index: TranscriptIndex,
        store: SpeakerLabelStore,
        file_manager: FileManagerFacade,
    ) -> None:
        self.index = index
        self.store = store
        self.file_manager = file_manager

    def roster(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str | None = None,
    ) -> tuple[SpeakerRosterEntry, ...]:
        document = self._document(
            document_id,
            expected_canonical_sha256=expected_canonical_sha256,
        )
        refs = canonical_speaker_refs(document, self.file_manager)
        labels = {
            item.speaker_ref: item.label for item in self.store.current_labels(document)
        }
        return tuple(
            SpeakerRosterEntry(speaker_ref=ref, display_label=labels.get(ref))
            for ref in refs
        )

    def views(self, document_id: str) -> tuple[SpeakerLabelView, ...]:
        return self.store.views(self._document(document_id))

    def set_label(
        self,
        document_id: str,
        *,
        speaker_ref: str,
        label: str,
        expected_canonical_sha256: str | None = None,
    ) -> SpeakerDisplayLabel:
        document = self._document(
            document_id,
            expected_canonical_sha256=expected_canonical_sha256,
        )
        refs = canonical_speaker_refs(document, self.file_manager)
        if speaker_ref not in refs:
            raise SpeakerLabelStateError(
                "Speaker reference is not present in the current canonical transcript"
            )
        return self.store.set_label(document, speaker_ref=speaker_ref, label=label)

    def remove_label(
        self,
        document_id: str,
        *,
        speaker_ref: str,
        expected_canonical_sha256: str | None = None,
    ) -> bool:
        document = self._document(
            document_id,
            expected_canonical_sha256=expected_canonical_sha256,
        )
        return self.store.remove_label(document, speaker_ref=speaker_ref)

    def display_labels(
        self,
        *,
        document_id: str,
        canonical_sha256: str | None,
        speaker_refs: tuple[str, ...],
    ) -> dict[str, str]:
        """Resolve labels for one exact canonical generation with one state read."""
        if canonical_sha256 is None or not speaker_refs:
            return {}
        document = self._document(document_id)
        if document.canonical_sha256 != canonical_sha256:
            return {}
        requested = set(speaker_refs)
        return {
            item.speaker_ref: item.label
            for item in self.store.current_labels(document)
            if item.speaker_ref in requested
        }

    def _document(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str | None = None,
    ) -> IndexedDocument:
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
        if (
            expected_canonical_sha256 is not None
            and document.canonical_sha256 != expected_canonical_sha256
        ):
            raise SpeakerLabelStateError(
                "Transcript changed since this view was opened; reopen it before editing speaker names"
            )
        return document
