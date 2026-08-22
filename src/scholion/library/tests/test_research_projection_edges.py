import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import scholion.library.research_projector as projector_module
from scholion.library.duckdb_research_projection import DuckDbResearchProjection
from scholion.library.errors import ResearchProjectionError, ResearchStateError
from scholion.library.evidence import EvidenceAnchor
from scholion.library.research_projection import ResearchProjectionFilter
from scholion.library.research_projector import ResearchStateProjector
from scholion.library.research_state import ResearchStateChange
from scholion.library.sqlite_research_state import SqliteResearchStateStore


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _anchor(
    *,
    segment_id: str = "segment-000042",
    canonical_digit: str = "1",
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path="/private/job-1.json",
        source_path="/private/job-1.wav",
        segment_ids=(segment_id,),
        start_seconds=42.0,
        end_seconds=45.0,
    )


def _state(tmp_path: Path) -> SqliteResearchStateStore:
    return SqliteResearchStateStore(
        tmp_path / "state" / "research.sqlite3",
        PrivateDirectoryStore(),  # type: ignore[arg-type]
    )


def _projection(tmp_path: Path) -> DuckDbResearchProjection:
    return DuckDbResearchProjection(
        tmp_path / "projection" / "research.duckdb",
        PrivateDirectoryStore(),  # type: ignore[arg-type]
    )


def test_projection_returns_generation_aware_evidence_and_empty_relationship_summaries(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)
    tagged = state.create_note(
        _anchor(segment_id="segment-000042"),
        "Housing methodology evidence",
        tags=("methodology",),
        collections=("Chapter 3",),
        note_id="note-tagged",
    )
    unlabelled = state.create_note(
        _anchor(segment_id="segment-000043"),
        "Housing follow up",
        note_id="note-unlabelled",
    )
    snapshot = state.projection_snapshot()
    projection.rebuild(snapshot.records, through_sequence=snapshot.sequence_id)
    methodology = state.resolve_tag_ids(("methodology",))
    assert methodology is not None

    tagged_scope = projection.matching_evidence(
        ResearchProjectionFilter(tag_ids=methodology)
    )
    all_scope = projection.matching_evidence(
        ResearchProjectionFilter(require_notes=True)
    )

    assert tagged_scope == (("job-1", "1" * 64, "segment-000042"),)
    assert all_scope == (
        ("job-1", "1" * 64, "segment-000042"),
        ("job-1", "1" * 64, "segment-000043"),
    )
    assert projection.matching_evidence(ResearchProjectionFilter(note_text="!!!")) == ()

    summaries = projection.summaries(all_scope)
    assert summaries[tagged_scope[0]].tag_ids == tagged.tag_ids
    assert summaries[tagged_scope[0]].collection_ids == tagged.collection_ids
    assert summaries[all_scope[1]].note_ids == (unlabelled.note_id,)
    assert summaries[all_scope[1]].tag_ids == ()
    assert summaries[all_scope[1]].collection_ids == ()


def test_projector_rejects_invalid_budget_configuration(tmp_path: Path) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)

    for batch_size in (0, 10_001):
        with pytest.raises(ValueError, match="batch_size"):
            ResearchStateProjector(state, projection, batch_size=batch_size)
    with pytest.raises(ValueError, match="retained_changes"):
        ResearchStateProjector(state, projection, retained_changes=-1)


def test_projector_fails_closed_when_projection_is_ahead_of_authority(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)
    projection.rebuild((), through_sequence=1)

    with pytest.raises(ResearchProjectionError, match="ahead of authoritative"):
        ResearchStateProjector(state, projection).sync()

    assert state.current_sequence() == 0
    assert projection.projected_through_sequence() == 1


def test_projector_enforces_bounded_convergence_budget(monkeypatch) -> None:
    monkeypatch.setattr(projector_module, "_MAX_SYNC_BATCHES", 2)
    store = Mock()
    projection = Mock()
    projection.projected_through_sequence.return_value = 0
    store.current_sequence.return_value = 3
    store.oldest_change_sequence.return_value = 1
    store.changes_after.side_effect = (
        (ResearchStateChange(1, "note-1"),),
        (ResearchStateChange(2, "note-2"),),
    )
    store.projection_records.return_value = ()
    projector = ResearchStateProjector(store, projection, batch_size=1)

    with pytest.raises(ResearchProjectionError, match="bounded sync budget"):
        projector.sync()

    assert store.changes_after.call_count == 2
    assert projection.apply.call_count == 2
    projection.apply.assert_any_call(
        (), deleted_note_ids=("note-1",), through_sequence=1
    )
    projection.apply.assert_any_call(
        (), deleted_note_ids=("note-2",), through_sequence=2
    )
    store.compact_changes.assert_not_called()


def test_sqlite_bounds_large_user_inputs_without_mutating_authority(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)

    with pytest.raises(ValueError, match="body is too large"):
        state.create_note(_anchor(), "x" * 1_000_001, note_id="note-large-body")
    with pytest.raises(ValueError, match="note_id is too long"):
        state.create_note(_anchor(), "body", note_id="n" * 201)
    with pytest.raises(ValueError, match="label name is too long"):
        state.create_note(
            _anchor(),
            "body",
            tags=("t" * 201,),
            note_id="note-large-tag",
        )
    with pytest.raises(ValueError, match="more than 10000"):
        state.notes_by_ids(tuple(f"note-{index}" for index in range(10_001)))

    assert state.current_sequence() == 0
    assert state.notes() == ()


def test_sqlite_projection_helpers_handle_empty_duplicate_and_noop_compaction(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    state.create_note(_anchor(), "body", note_id="note-1")
    changes_before = state.changes_after(0, limit=10)

    assert state.projection_records(()) == ()
    with pytest.raises(ValueError, match="duplicates"):
        state.projection_records(("note-1", "note-1"))

    state.compact_changes(1, retain=5)

    assert state.changes_after(0, limit=10) == changes_before
    assert state.current_sequence() == 1


def test_sqlite_missing_metadata_rolls_back_mutation_and_surfaces_corruption(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "research.sqlite3"
    state = _state(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM metadata WHERE singleton = 1")
        connection.commit()

    with pytest.raises(ResearchStateError, match="metadata is missing"):
        state.create_note(_anchor(), "must roll back", note_id="note-1")
    with pytest.raises(ResearchStateError, match="metadata is missing"):
        state.current_sequence()

    with sqlite3.connect(path) as connection:
        stored_notes = connection.execute("SELECT COUNT(*) FROM notes").fetchone()
    assert stored_notes == (0,)
