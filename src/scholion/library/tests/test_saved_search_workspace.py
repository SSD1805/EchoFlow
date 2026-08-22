from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from scholion.library.duckdb_research_projection import DuckDbResearchProjection
from scholion.library.evidence import EvidenceAnchor
from scholion.library.index import IndexedDocument, SearchQuery
from scholion.library.research_projector import ResearchStateProjector
from scholion.library.research_workspace import (
    ResearchQueryFilters,
    ResearchWorkspaceService,
)
from scholion.library.retrieval import RetrievalMode
from scholion.library.sqlite_research_state import SqliteResearchStateStore
from scholion.library.workspace_metadata import SqliteWorkspaceMetadataStore


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _anchor(segment_id: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/job-1.json",
        source_path="/private/job-1.wav",
        segment_ids=(segment_id,),
        start_seconds=1.0,
        end_seconds=2.0,
    )


def _workspace(tmp_path: Path):
    file_store = PrivateDirectoryStore()
    state_path = tmp_path / "state" / "research.sqlite3"
    state = SqliteResearchStateStore(
        state_path,
        file_store,  # type: ignore[arg-type]
    )
    metadata = SqliteWorkspaceMetadataStore(
        state_path,
        file_store,  # type: ignore[arg-type]
    )
    projection = DuckDbResearchProjection(
        tmp_path / "projection" / "research.duckdb",
        file_store,  # type: ignore[arg-type]
    )
    projector = ResearchStateProjector(state, projection, batch_size=1)
    transcript_library = Mock()
    transcript_library.documents.return_value = (
        IndexedDocument(
            document_id="job-1",
            source_sha256="0" * 64,
            canonical_sha256="1" * 64,
            detected_language="en",
            canonical_path="/private/job-1.json",
            source_path="/private/job-1.wav",
            segment_count=10,
        ),
    )
    navigation = Mock()
    navigation.search.return_value = SimpleNamespace(results=())
    workspace = ResearchWorkspaceService(
        transcript_library,
        Mock(),
        navigation,
        state,
        projection,
        projector,
        metadata,
    )
    return workspace, state, navigation


def test_saved_search_replays_typed_intent_against_current_research_scope(
    tmp_path: Path,
) -> None:
    workspace, state, navigation = _workspace(tmp_path)
    state.create_note(
        _anchor("segment-000001"),
        "first note",
        tags=("housing",),
        note_id="note-1",
    )
    saved = workspace.save_search(
        "Housing evidence",
        SearchQuery("rent burden", document_ids=("job-1",), limit=25),
        filters=ResearchQueryFilters(tags=("housing",), with_notes=True),
        mode=RetrievalMode.HYBRID,
        context_segments=2,
        description="Reusable housing evidence query",
        saved_search_id="search-housing",
    )

    assert saved.intent.query.evidence_scope is None
    assert saved.intent.tags == ("housing",)
    assert saved.intent.with_notes
    assert saved.intent.mode is RetrievalMode.HYBRID
    assert saved.intent.context_segments == 2

    workspace.run_saved_search("Housing evidence")
    first_runtime_query = navigation.search.call_args.args[0]
    assert first_runtime_query.evidence_scope == (
        ("job-1", "1" * 64, "segment-000001"),
    )
    assert navigation.search.call_args.kwargs == {
        "mode": RetrievalMode.HYBRID,
        "context_segments": 2,
    }

    state.create_note(
        _anchor("segment-000002"),
        "second note",
        tags=("housing",),
        note_id="note-2",
    )
    workspace.run_saved_search(saved.saved_search_id)
    second_runtime_query = navigation.search.call_args.args[0]

    assert saved.intent.query.evidence_scope is None
    assert second_runtime_query.evidence_scope == (
        ("job-1", "1" * 64, "segment-000001"),
        ("job-1", "1" * 64, "segment-000002"),
    )


def test_workspace_navigation_reads_live_relationships_not_saved_counters(
    tmp_path: Path,
) -> None:
    workspace, state, _ = _workspace(tmp_path)
    first = state.create_note(
        _anchor("segment-000001"),
        "one",
        tags=("housing",),
        collections=("Chapter 1",),
        note_id="note-1",
    )
    state.create_note(
        _anchor("segment-000002"),
        "two",
        tags=("housing", "methods"),
        collections=("Chapter 1",),
        note_id="note-2",
    )

    before = workspace.workspace_navigation()
    assert before.frequent_tags[0].name == "housing"
    assert before.frequent_tags[0].usage_count == 2
    assert before.frequent_collections[0].name == "Chapter 1"
    assert before.frequent_collections[0].usage_count == 2

    state.set_note_tags(first.note_id, ("methods",))
    state.set_note_collections(first.note_id, ("Appendix",))
    after = workspace.workspace_navigation()

    assert [(item.name, item.usage_count) for item in after.frequent_tags] == [
        ("methods", 2),
        ("housing", 1),
    ]
    assert [(item.name, item.usage_count) for item in after.frequent_collections] == [
        ("Appendix", 1),
        ("Chapter 1", 1),
    ]
