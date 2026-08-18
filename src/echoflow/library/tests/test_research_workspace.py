from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from echoflow.library.duckdb_research_projection import DuckDbResearchProjection
from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.index import IndexedDocument, SearchQuery
from echoflow.library.research_projector import ResearchStateProjector
from echoflow.library.research_workspace import (
    ResearchEvidenceView,
    ResearchQueryFilters,
    ResearchWorkspaceService,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.sqlite_research_state import SqliteResearchStateStore


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _anchor(
    *,
    document_id: str = "job-1",
    canonical_digit: str = "1",
    segment_ids: tuple[str, ...] = ("segment-000042",),
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id=document_id,
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/private/{document_id}.json",
        source_path=f"/private/{document_id}.wav",
        segment_ids=segment_ids,
        start_seconds=42.0,
        end_seconds=45.0,
    )


def _document(*, canonical_digit: str = "1") -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        detected_language="en",
        canonical_path="/private/job-1.json",
        source_path="/private/job-1.wav",
        segment_count=100,
    )


def _workspace(tmp_path: Path):
    file_store = PrivateDirectoryStore()
    state = SqliteResearchStateStore(
        tmp_path / "state" / "research.sqlite3",
        file_store,  # type: ignore[arg-type]
    )
    projection = DuckDbResearchProjection(
        tmp_path / "projection" / "research.duckdb",
        file_store,  # type: ignore[arg-type]
    )
    projector = ResearchStateProjector(state, projection, batch_size=1)
    transcript_library = Mock()
    transcript_library.documents.return_value = (_document(),)
    evidence_locator = Mock()
    navigation = Mock()
    workspace = ResearchWorkspaceService(
        transcript_library,
        evidence_locator,
        navigation,
        state,
        projection,
        projector,
    )
    return workspace, state, projection, projector, transcript_library, evidence_locator, navigation


def _located(*, segment_ids: tuple[str, ...] = ("segment-000042",)):
    evidence = SimpleNamespace(
        document_id="job-1",
        canonical_sha256="1" * 64,
        result_segment_ids=segment_ids,
    )
    return SimpleNamespace(evidence=evidence)


def test_workspace_search_compiles_human_filters_before_navigation_and_decorates_results(
    tmp_path: Path,
) -> None:
    workspace, state, _, _, _, _, navigation = _workspace(tmp_path)
    note = state.create_note(
        _anchor(segment_ids=("segment-000041", "segment-000042")),
        "Housing affordability methodology",
        tags=("methodology", "housing"),
        collections=("Chapter 3",),
        note_id="note-1",
    )
    located = _located(segment_ids=("segment-000041", "segment-000042"))
    navigation.search.return_value = SimpleNamespace(results=(located,))
    query = SearchQuery("housing", document_ids=("job-1",))

    response = workspace.search(
        query,
        filters=ResearchQueryFilters(
            tags=("METHODOLOGY",),
            collections=("chapter 3",),
            note_text="affordability",
            with_notes=True,
        ),
        mode=RetrievalMode.LEXICAL,
        context_segments=2,
    )

    scoped_query = navigation.search.call_args.args[0]
    assert scoped_query.text == "housing"
    assert scoped_query.document_ids == ("job-1",)
    assert scoped_query.evidence_scope == (
        ("job-1", "1" * 64, "segment-000041"),
        ("job-1", "1" * 64, "segment-000042"),
    )
    assert navigation.search.call_args.kwargs == {
        "mode": RetrievalMode.LEXICAL,
        "context_segments": 2,
    }
    assert response.results[0].located is located
    assert response.results[0].research.note_ids == (note.note_id,)
    assert response.results[0].research.tags == ("housing", "methodology")
    assert response.results[0].research.collections == ("Chapter 3",)
    assert response.results[0].research.note_count == 1


def test_workspace_unknown_research_label_compiles_to_empty_evidence_scope(
    tmp_path: Path,
) -> None:
    workspace, state, _, _, _, _, navigation = _workspace(tmp_path)
    state.create_note(
        _anchor(),
        "Housing note",
        tags=("known",),
        note_id="note-1",
    )
    navigation.search.return_value = SimpleNamespace(results=())

    response = workspace.search(
        SearchQuery("housing"),
        filters=ResearchQueryFilters(tags=("missing",)),
    )

    scoped_query = navigation.search.call_args.args[0]
    assert scoped_query.evidence_scope == ()
    assert response.results == ()


def test_workspace_unfiltered_search_preserves_unrestricted_query(tmp_path: Path) -> None:
    workspace, _, _, projector, _, _, navigation = _workspace(tmp_path)
    located = _located()
    navigation.search.return_value = SimpleNamespace(results=(located,))
    query = SearchQuery("housing")

    response = workspace.search(query)

    searched = navigation.search.call_args.args[0]
    assert searched is query
    assert searched.evidence_scope is None
    assert response.results[0].research == ResearchEvidenceView()
    assert projector.status().current


def test_workspace_note_mutations_use_verified_anchor_and_preserve_currentness(
    tmp_path: Path,
) -> None:
    (
        workspace,
        state,
        _,
        _,
        transcript_library,
        evidence_locator,
        _,
    ) = _workspace(tmp_path)
    anchor = _anchor()
    evidence_locator.resolve_anchor.return_value = anchor

    created = workspace.add_note(
        "job-1",
        ("segment-000042",),
        "Initial observation",
        tags=("methodology",),
        collections=("Chapter 3",),
        start_seconds=42.25,
        end_seconds=44.75,
    )

    evidence_locator.resolve_anchor.assert_called_once_with(
        _document(),
        ("segment-000042",),
        start_seconds=42.25,
        end_seconds=44.75,
    )
    assert created.current
    assert created.note.anchor == anchor
    assert created.tags == ("methodology",)
    assert created.collections == ("Chapter 3",)

    updated = workspace.update_note(created.note.note_id, "Revised observation")
    retagged = workspace.set_note_tags(created.note.note_id, ("evidence",))
    recollected = workspace.set_note_collections(created.note.note_id, ("Chapter 4",))

    assert updated.note.body == "Revised observation"
    assert retagged.tags == ("evidence",)
    assert recollected.collections == ("Chapter 4",)
    assert workspace.note(created.note.note_id) is not None
    assert state.current_sequence() == 4

    transcript_library.documents.return_value = (_document(canonical_digit="2"),)
    stale = workspace.note(created.note.note_id)
    assert stale is not None
    assert not stale.current

    workspace.delete_note(created.note.note_id)
    assert workspace.note(created.note.note_id) is None
    assert state.current_sequence() == 5


def test_workspace_add_note_refuses_unknown_document_before_anchor_resolution(
    tmp_path: Path,
) -> None:
    workspace, _, _, _, transcript_library, evidence_locator, _ = _workspace(tmp_path)
    transcript_library.documents.return_value = ()

    with pytest.raises(ResearchStateError, match="not present"):
        workspace.add_note("missing", ("segment-1",), "body")

    evidence_locator.resolve_anchor.assert_not_called()


def test_workspace_filtered_note_listing_uses_projection_and_authoritative_batch_read(
    tmp_path: Path,
) -> None:
    workspace, state, _, _, _, _, _ = _workspace(tmp_path)
    first = state.create_note(
        _anchor(),
        "Housing methodology note",
        tags=("methodology",),
        note_id="note-1",
    )
    state.create_note(
        _anchor(segment_ids=("segment-000043",)),
        "Housing follow up",
        tags=("follow-up",),
        note_id="note-2",
    )

    methodology = workspace.notes(
        filters=ResearchQueryFilters(tags=("methodology",)),
        limit=10,
    )
    textual = workspace.notes(
        document_id="job-1",
        filters=ResearchQueryFilters(note_text="methodology"),
        limit=10,
    )
    missing = workspace.notes(
        filters=ResearchQueryFilters(collections=("does-not-exist",)),
        limit=10,
    )
    all_notes = workspace.notes(limit=10)

    assert tuple(view.note.note_id for view in methodology) == (first.note_id,)
    assert tuple(view.note.note_id for view in textual) == (first.note_id,)
    assert missing == ()
    assert {view.note.note_id for view in all_notes} == {"note-1", "note-2"}
    assert all(view.current for view in all_notes)

    with pytest.raises(ValueError, match="limit"):
        workspace.notes(limit=0)
    with pytest.raises(ValueError, match="limit"):
        workspace.notes(limit=10_001)


def test_workspace_exposes_tags_collections_and_projection_recovery_controls(
    tmp_path: Path,
) -> None:
    workspace, state, projection, _, _, _, _ = _workspace(tmp_path)
    state.create_note(
        _anchor(),
        "body",
        tags=("methodology",),
        collections=("Chapter 3",),
        note_id="note-1",
    )

    status_before = workspace.projection_status()
    synced = workspace.sync_projection()

    assert not status_before.current
    assert synced.current
    assert tuple(tag.name for tag in workspace.tags()) == ("methodology",)
    assert tuple(collection.name for collection in workspace.collections()) == ("Chapter 3",)

    projection.clear()
    rebuilt = workspace.rebuild_projection()
    assert rebuilt.rebuilt
    assert rebuilt.current
    assert workspace.projection_status().current


def test_workspace_contracts_reject_ambiguous_filters_and_result_reordering() -> None:
    with pytest.raises(ValueError, match="blank"):
        ResearchQueryFilters(tags=("",))
    with pytest.raises(ValueError, match="duplicates"):
        ResearchQueryFilters(tags=("Methodology", " methodology "))
    with pytest.raises(ValueError, match="duplicates"):
        ResearchQueryFilters(collections=("Chapter 3", "chapter 3"))
    with pytest.raises(ValueError, match="note_text"):
        ResearchQueryFilters(note_text=" ")

    assert not ResearchQueryFilters().active
    assert ResearchQueryFilters(with_notes=True).active

    first = SimpleNamespace(name="first")
    second = SimpleNamespace(name="second")
    navigation = SimpleNamespace(results=(first, second))
    with pytest.raises(ValueError, match="cardinality"):
        WorkspaceSearchResponse(navigation, ResearchQueryFilters(), ())

    results = (
        WorkspaceSearchPassage(second, ResearchEvidenceView()),
        WorkspaceSearchPassage(first, ResearchEvidenceView()),
    )
    with pytest.raises(ValueError, match="order"):
        WorkspaceSearchResponse(navigation, ResearchQueryFilters(), results)
