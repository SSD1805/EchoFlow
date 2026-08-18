from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from echoflow.library.duckdb_research_projection import DuckDbResearchProjection
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.index import IndexedDocument
from echoflow.library.research_projector import ResearchStateProjector
from echoflow.library.research_workspace import ResearchWorkspaceService
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
    canonical_digit: str = "1",
    segment_id: str = "segment-000042",
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path="/private/job-1.json",
        source_path="/private/interview.wav",
        segment_ids=(segment_id,),
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
        source_path="/private/interview.wav",
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
    navigation = Mock()
    evidence_locator = Mock()
    workspace = ResearchWorkspaceService(
        transcript_library,
        evidence_locator,
        navigation,
        state,
        projection,
        projector,
    )
    return workspace, state, transcript_library, navigation


def _located(segment_id: str = "segment-000042"):
    return SimpleNamespace(
        evidence=SimpleNamespace(
            document_id="job-1",
            canonical_sha256="1" * 64,
            result_segment_ids=(segment_id,),
        )
    )


def _navigation_result(query, *, mode: RetrievalMode, results=()):
    return SimpleNamespace(
        retrieval=SimpleNamespace(query=query, mode=mode),
        results=results,
    )


def test_discover_returns_grouped_transcript_and_authoritative_research_results(
    tmp_path: Path,
) -> None:
    workspace, state, _, navigation = _workspace(tmp_path)
    housing_note = state.create_note(
        _anchor(),
        "Housing affordability methodology",
        tags=("housing", "methodology"),
        collections=("Housing interviews",),
        note_id="note-housing",
    )
    state.create_note(
        _anchor(segment_id="segment-000043"),
        "Budget follow up",
        tags=("budget",),
        collections=("Finance",),
        note_id="note-budget",
    )
    located = _located()

    def search(query, *, mode: RetrievalMode, context_segments: int):
        assert context_segments == 2
        return _navigation_result(query, mode=mode, results=(located,))

    navigation.search.side_effect = search

    response = workspace.discover(
        "  housing  ",
        mode=RetrievalMode.HYBRID,
        limit=10,
        context_segments=2,
    )

    searched_query = navigation.search.call_args.args[0]
    assert searched_query.text == "housing"
    assert searched_query.limit == 10
    assert navigation.search.call_args.kwargs["mode"] is RetrievalMode.HYBRID
    assert response.query == "housing"
    assert response.transcripts.results[0].located is located
    assert tuple(view.note.note_id for view in response.notes) == (housing_note.note_id,)
    assert response.notes[0].note.body == "Housing affordability methodology"
    assert response.notes[0].current
    assert tuple(tag.name for tag in response.tags) == ("housing",)
    assert tuple(collection.name for collection in response.collections) == (
        "Housing interviews",
    )
    assert response.total_count == 4


def test_discovery_name_matching_is_group_local_and_deterministic(tmp_path: Path) -> None:
    workspace, state, _, navigation = _workspace(tmp_path)
    state.create_note(
        _anchor(),
        "housing affordability",
        tags=("housing", "Housing affordability", "social housing", "affordability"),
        collections=("Housing affordability", "Housing interviews"),
        note_id="note-1",
    )
    navigation.search.side_effect = lambda query, **kwargs: _navigation_result(
        query,
        mode=kwargs["mode"],
    )

    response = workspace.discover("housing affordability", limit=10)

    assert response.tags[0].name == "Housing affordability"
    assert {tag.name for tag in response.tags} == {
        "Housing affordability",
        "housing",
        "social housing",
        "affordability",
    }
    assert response.collections[0].name == "Housing affordability"
    assert {collection.name for collection in response.collections} == {
        "Housing affordability",
        "Housing interviews",
    }


def test_discovery_preserves_stale_notes_instead_of_reattaching_or_hiding_them(
    tmp_path: Path,
) -> None:
    workspace, state, transcript_library, navigation = _workspace(tmp_path)
    note = state.create_note(
        _anchor(canonical_digit="1"),
        "Housing observation from the older transcript",
        tags=("housing",),
        note_id="note-old",
    )
    transcript_library.documents.return_value = (_document(canonical_digit="2"),)
    navigation.search.side_effect = lambda query, **kwargs: _navigation_result(
        query,
        mode=kwargs["mode"],
    )

    response = workspace.discover("housing")

    assert tuple(view.note.note_id for view in response.notes) == (note.note_id,)
    assert not response.notes[0].current
    assert response.notes[0].note.anchor.canonical_sha256 == "1" * 64
    assert response.tags[0].name == "housing"
    assert response.transcripts.results == ()


def test_discovery_validates_human_query_limits_before_running_retrieval(
    tmp_path: Path,
) -> None:
    workspace, _, _, navigation = _workspace(tmp_path)

    with pytest.raises(ValueError, match="query"):
        workspace.discover("   ")
    with pytest.raises(ValueError, match="limit"):
        workspace.discover("housing", limit=0)
    with pytest.raises(ValueError, match="limit"):
        workspace.discover("housing", limit=101)
    with pytest.raises(ValueError, match="context_segments"):
        workspace.discover("housing", context_segments=11)

    navigation.search.assert_not_called()
