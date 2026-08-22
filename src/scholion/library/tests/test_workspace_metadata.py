import sqlite3
from pathlib import Path

import pytest

from scholion.library.errors import ResearchStateError
from scholion.library.evidence import EvidenceAnchor
from scholion.library.index import SearchOperator, SearchQuery, SearchSort
from scholion.library.retrieval import RetrievalMode
from scholion.library.sqlite_research_state import SqliteResearchStateStore
from scholion.library.workspace_metadata import (
    SavedSearchIntent,
    SqliteWorkspaceMetadataStore,
)


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _stores(tmp_path: Path):
    path = tmp_path / "state" / "research.sqlite3"
    file_store = PrivateDirectoryStore()
    research = SqliteResearchStateStore(
        path,
        file_store,  # type: ignore[arg-type]
    )
    metadata = SqliteWorkspaceMetadataStore(
        path,
        file_store,  # type: ignore[arg-type]
    )
    return research, metadata, path


def _anchor(segment: int) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/job-1.json",
        source_path="/private/job-1.wav",
        segment_ids=(f"segment-{segment:06d}",),
        start_seconds=float(segment),
        end_seconds=float(segment + 1),
    )


def _intent(*, text: str = "housing affordability") -> SavedSearchIntent:
    return SavedSearchIntent(
        query=SearchQuery(
            text=text,
            phrase=True,
            operator=SearchOperator.ALL,
            speaker_refs=("speaker-02",),
            languages=("en",),
            document_ids=("job-1",),
            sort=SearchSort.TIMELINE,
            limit=17,
        ),
        mode=RetrievalMode.HYBRID,
        context_segments=2,
        tags=("methodology",),
        collections=("Chapter 3",),
        note_text="rent burden",
        with_notes=True,
    )


def test_saved_search_round_trip_preserves_typed_intent(tmp_path: Path) -> None:
    _, metadata, _ = _stores(tmp_path)
    intent = _intent()

    created = metadata.create_saved_search(
        "Housing chapter",
        intent,
        description="Interview evidence for the housing chapter",
        saved_search_id="search-housing",
    )

    assert created.intent == intent
    assert metadata.saved_search("search-housing") == created
    assert metadata.saved_search("  HOUSING CHAPTER  ") == created
    assert metadata.saved_searches() == (created,)

    replacement = SavedSearchIntent(
        query=SearchQuery("tenant protections", limit=25),
        mode=RetrievalMode.LEXICAL,
        tags=("policy",),
    )
    updated = metadata.update_saved_search(
        created.saved_search_id,
        name="Tenant protections",
        description=None,
        intent=replacement,
    )

    assert updated.saved_search_id == created.saved_search_id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert updated.intent == replacement
    assert metadata.saved_search("tenant protections") == updated
    assert metadata.saved_search("Housing chapter") is None

    metadata.delete_saved_search(updated.saved_search_id)
    assert metadata.saved_searches() == ()


def test_saved_search_rejects_derived_evidence_scope() -> None:
    with pytest.raises(ValueError, match="derived evidence scope"):
        SavedSearchIntent(
            query=SearchQuery(
                "housing",
                evidence_scope=(("job-1", "1" * 64, "segment-000001"),),
            )
        )


def test_saved_search_names_are_casefold_unique_without_overwrite(
    tmp_path: Path,
) -> None:
    _, metadata, _ = _stores(tmp_path)
    original = metadata.create_saved_search(
        "Methods",
        _intent(text="methodology"),
        saved_search_id="search-1",
    )

    with pytest.raises(ResearchStateError, match="already exists"):
        metadata.create_saved_search(
            "  METHODS  ",
            _intent(text="different"),
            saved_search_id="search-2",
        )

    assert metadata.saved_searches() == (original,)


def test_navigation_derives_usage_and_recency_from_current_relationships(
    tmp_path: Path,
) -> None:
    research, metadata, _ = _stores(tmp_path)
    research.create_note(
        _anchor(1),
        "First",
        tags=("housing", "methodology"),
        collections=("Chapter 1",),
        note_id="note-1",
    )
    research.create_note(
        _anchor(2),
        "Second",
        tags=("housing",),
        collections=("Appendix",),
        note_id="note-2",
    )
    research.create_note(
        _anchor(3),
        "Third",
        tags=("housing",),
        collections=("Chapter 1",),
        note_id="note-3",
    )

    navigation = metadata.navigation(limit=10)

    assert [(item.name, item.usage_count) for item in navigation.frequent_tags] == [
        ("housing", 3),
        ("methodology", 1),
    ]
    assert navigation.recent_tags[0].name == "housing"
    assert [
        (item.name, item.usage_count) for item in navigation.frequent_collections
    ] == [
        ("Chapter 1", 2),
        ("Appendix", 1),
    ]
    assert navigation.recent_collections[0].name == "Chapter 1"

    research.set_note_tags("note-3", ("methodology",))
    refreshed = metadata.navigation(limit=10)

    # Frequency ties deliberately fall through to recency. The newly-used
    # methodology relationship therefore sorts ahead of housing at count 2.
    assert [(item.name, item.usage_count) for item in refreshed.frequent_tags] == [
        ("methodology", 2),
        ("housing", 2),
    ]
    assert refreshed.recent_tags[0].name == "methodology"


def test_navigation_is_bounded_and_does_not_persist_counters(tmp_path: Path) -> None:
    research, metadata, path = _stores(tmp_path)
    research.create_note(
        _anchor(1),
        "One",
        tags=("a", "b"),
        collections=("one", "two"),
        note_id="note-1",
    )

    assert len(metadata.navigation(limit=1).frequent_tags) == 1
    assert len(metadata.navigation(limit=1).frequent_collections) == 1
    with pytest.raises(ValueError, match="navigation limit"):
        metadata.navigation(limit=0)

    with sqlite3.connect(path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(tags)").fetchall()
        }
        collection_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(collections)").fetchall()
        }
    assert "usage_count" not in columns
    assert "last_used_at" not in columns
    assert "usage_count" not in collection_columns
    assert "last_used_at" not in collection_columns


def test_workspace_metadata_rejects_unsupported_schema(tmp_path: Path) -> None:
    _, _, path = _stores(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE workspace_metadata SET schema_version = 999 WHERE singleton = 1"
        )
        connection.commit()

    with pytest.raises(ResearchStateError, match="schema is unsupported"):
        SqliteWorkspaceMetadataStore(
            path,
            PrivateDirectoryStore(),  # type: ignore[arg-type]
        )
