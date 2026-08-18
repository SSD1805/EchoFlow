"""Application service for human-readable names over anonymous speaker evidence."""

from __future__ import annotations

from dataclasses import dataclass

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import SpeakerLabelStateError
from echoflow.library.index import IndexedDocument, TranscriptIndex
from echoflow.library.speaker_labels import (
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

    def roster(self, document_id: str) -> tuple[SpeakerRosterEntry, ...]:
        document = self._document(document_id)
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
    ) -> SpeakerDisplayLabel:
        document = self._document(document_id)
        refs = canonical_speaker_refs(document, self.file_manager)
        if speaker_ref not in refs:
            raise SpeakerLabelStateError(
                "Speaker reference is not present in the current canonical transcript"
            )
        return self.store.set_label(document, speaker_ref=speaker_ref, label=label)

    def remove_label(self, document_id: str, *, speaker_ref: str) -> bool:
        return self.store.remove_label(
            self._document(document_id), speaker_ref=speaker_ref
        )

    def display_labels(
        self,
        *,
        document_id: str,
        canonical_sha256: str | None,
        speaker_refs: tuple[str, ...],
    ) -> dict[str, str]:
        """Resolve only labels bound to the exact evidence generation in a result."""
        return {
            speaker_ref: label
            for speaker_ref in speaker_refs
            if (
                label := self.store.resolve(
                    document_id=document_id,
                    canonical_sha256=canonical_sha256,
                    speaker_ref=speaker_ref,
                )
            )
            is not None
        }

    def _document(self, document_id: str) -> IndexedDocument:
        document = next(
            (item for item in self.index.documents() if item.document_id == document_id),
            None,
        )
        if document is None:
            raise SpeakerLabelStateError(
                "Transcript is not present in the local library; rebuild the library first"
            )
        return document
