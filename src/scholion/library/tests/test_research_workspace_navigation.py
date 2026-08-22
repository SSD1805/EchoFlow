from unittest.mock import Mock

import pytest

from scholion.core.ilogger import ILogger
from scholion.library.errors import EvidenceNavigationError
from scholion.library.evidence import (
    EvidenceAnchor,
    EvidenceContextSegment,
    EvidenceLocation,
)
from scholion.library.index import IndexedDocument, SearchQuery
from scholion.library.research import LocatedCanonicalEvidence, SpeakerDisplay
from scholion.library.research_state import ResearchNote
from scholion.library.research_workspace import ResearchWorkspaceService
from scholion.library.workspace_metadata import SavedSearch, SavedSearchIntent


def _anchor() -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
        canonical_path="/private/old-generation.json",
        source_path="/private/recording.wav",
        segment_ids=("segment-000002",),
        start_seconds=2.1,
        end_seconds=2.9,
    )


def _note() -> ResearchNote:
    return ResearchNote(
        note_id="note-1",
        body="Interpretation",
        anchor=_anchor(),
        tag_ids=(),
        collection_ids=(),
        created_at="2026-08-19T20:00:00+00:00",
        updated_at="2026-08-19T20:00:00+00:00",
    )


def _located(
    *,
    document_id: str = "job-1",
    canonical_sha256: str = "b" * 64,
) -> LocatedCanonicalEvidence:
    anchor = _anchor()
    evidence = EvidenceLocation(
        document_id=document_id,
        source_sha256=anchor.source_sha256,
        canonical_sha256=canonical_sha256,
        canonical_path=anchor.canonical_path,
        source_path=anchor.source_path,
        result_segment_ids=anchor.segment_ids,
        start_seconds=anchor.start_seconds,
        end_seconds=anchor.end_seconds,
        seek_seconds=anchor.start_seconds,
        result_speaker_refs=("speaker-01",),
        matched_words=(),
        context_segments=(
            EvidenceContextSegment(
                segment_id="segment-000002",
                start_seconds=2.0,
                end_seconds=3.0,
                text="Exact evidence",
                speaker_refs=("speaker-01",),
                words=(),
                is_result_segment=True,
                lexical_match=False,
            ),
        ),
    )
    return LocatedCanonicalEvidence(
        evidence=evidence,
        speakers=(SpeakerDisplay("speaker-01", "Participant A"),),
    )


def _workspace(
    *, logger: Mock | None = None
) -> tuple[ResearchWorkspaceService, Mock, Mock, Mock]:
    transcript_library = Mock()
    transcript_library.documents.return_value = (
        IndexedDocument(
            document_id="job-1",
            source_sha256="a" * 64,
            canonical_sha256="c" * 64,
            detected_language="en",
            canonical_path="/private/current.json",
            source_path="/private/recording.wav",
            segment_count=3,
        ),
    )
    state = Mock()
    state.note.return_value = _note()
    state.tags.return_value = ()
    state.collections.return_value = ()
    navigation = Mock()
    navigation.locate_anchor.return_value = _located()
    metadata = Mock()
    workspace = ResearchWorkspaceService(
        transcript_library,
        Mock(),
        navigation,
        state,
        Mock(),
        Mock(),
        metadata,
        logger=logger,
    )
    return workspace, navigation, metadata, state


def test_open_note_evidence_uses_stored_generation_without_rebinding() -> None:
    logger = Mock(spec=ILogger)
    workspace, navigation, _, _ = _workspace(logger=logger)

    opened = workspace.open_note_evidence("note-1", context_segments=2)

    assert not opened.note.current
    assert opened.located.evidence.canonical_sha256 == "b" * 64
    navigation.locate_anchor.assert_called_once_with(_anchor(), context_segments=2)
    logger.info.assert_called_once_with(
        "research_note_evidence_opened",
        note_id="note-1",
        document_id="job-1",
        canonical_sha256="b" * 64,
        current=False,
        context_segments=2,
    )


def test_open_note_evidence_rejects_document_identity_mismatch() -> None:
    workspace, navigation, _, _ = _workspace()
    navigation.locate_anchor.return_value = _located(document_id="job-2")

    with pytest.raises(ValueError, match="document identities must match"):
        workspace.open_note_evidence("note-1")


def test_open_note_evidence_rejects_canonical_generation_mismatch() -> None:
    workspace, navigation, _, _ = _workspace()
    navigation.locate_anchor.return_value = _located(canonical_sha256="d" * 64)

    with pytest.raises(ValueError, match="canonical generations must match"):
        workspace.open_note_evidence("note-1")


def test_open_note_evidence_logs_safe_failure_without_rebinding() -> None:
    logger = Mock(spec=ILogger)
    workspace, navigation, _, _ = _workspace(logger=logger)
    navigation.locate_anchor.side_effect = EvidenceNavigationError(
        "Canonical evidence could not be validated for navigation"
    )

    with pytest.raises(EvidenceNavigationError):
        workspace.open_note_evidence("note-1")

    logger.warning.assert_called_once_with(
        "research_note_evidence_open_failed",
        note_id="note-1",
        document_id="job-1",
        canonical_sha256="b" * 64,
        current=False,
        exception_type="EvidenceNavigationError",
    )


def test_rename_saved_search_preserves_typed_intent_and_passes_version() -> None:
    logger = Mock(spec=ILogger)
    workspace, _, metadata, _ = _workspace(logger=logger)
    intent = SavedSearchIntent(query=SearchQuery("housing", limit=20))
    saved = SavedSearch(
        saved_search_id="search-1",
        name="Housing",
        description=None,
        intent=intent,
        created_at="2026-08-19T20:00:00+00:00",
        updated_at="2026-08-19T20:00:00+00:00",
    )
    updated = SavedSearch(
        saved_search_id="search-1",
        name="Housing follow-up",
        description="Current questions",
        intent=intent,
        created_at=saved.created_at,
        updated_at="2026-08-19T20:01:00+00:00",
    )
    metadata.saved_search.return_value = saved
    metadata.update_saved_search.return_value = updated

    result = workspace.rename_saved_search(
        "search-1",
        name="Housing follow-up",
        description="Current questions",
        expected_updated_at=saved.updated_at,
    )

    assert result == updated
    metadata.update_saved_search.assert_called_once_with(
        "search-1",
        name="Housing follow-up",
        description="Current questions",
        intent=intent,
        expected_updated_at=saved.updated_at,
    )
    logger.info.assert_called_once_with(
        "research_saved_search_updated",
        saved_search_id="search-1",
    )
