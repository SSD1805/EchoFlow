import sqlite3
from pathlib import Path

import duckdb
import pytest

from echoflow.library.duckdb_research_projection import DuckDbResearchProjection
from echoflow.library.errors import ResearchProjectionError, ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_projection import (
    ProjectedEvidenceSummary,
    ResearchProjectionFilter,
    ResearchProjectionStatus,
)
from echoflow.library.research_projector import ResearchStateProjector
from echoflow.library.research_state import (
    ResearchCollection,
    ResearchNote,
    ResearchProjectionRecord,
    ResearchProjectionSnapshot,
    ResearchStateChange,
    ResearchTag,
)
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
    start_seconds: float = 42.0,
    end_seconds: float = 45.0,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id=document_id,
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/private/{document_id}.json",
        source_path=f"/private/{document_id}.wav",
        segment_ids=segment_ids,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
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


def test_sqlite_crud_preserves_relationships_order_and_outbox(tmp_path: Path) -> None:
    state = _state(tmp_path)
    first = state.create_note(
        _anchor(segment_ids=("segment-000041", "segment-000042")),
        "First observation",
        tags=(" Methodology ", "methodology", "Housing"),
        collections=("Chapter 3", " chapter 3 "),
        note_id="note-1",
    )
    second = state.create_note(
        _anchor(document_id="job-2", canonical_digit="2"),
        "Second observation",
        tags=("Follow-up",),
        collections=("Appendix",),
        note_id="note-2",
    )

    assert state.current_sequence() == 2
    assert first.anchor.segment_ids == ("segment-000041", "segment-000042")
    assert len(first.tag_ids) == 2
    assert len(first.collection_ids) == 1
    assert state.notes_by_ids(("note-2", "note-1")) == (second, first)
    assert tuple(note.note_id for note in state.notes(document_id="job-1")) == (
        "note-1",
    )
    assert state.notes_by_ids(("missing", "note-1")) == (first,)

    updated = state.update_note("note-1", "Revised observation")
    retagged = state.set_note_tags("note-1", ("Evidence", "housing"))
    recollected = state.set_note_collections("note-1", ("Chapter 4",))

    assert updated.body == "Revised observation"
    assert retagged.body == "Revised observation"
    assert {tag.name for tag in state.tags()} == {
        "Methodology",
        "Housing",
        "Follow-up",
        "Evidence",
    }
    assert state.resolve_tag_ids(("EVIDENCE", "housing")) == retagged.tag_ids
    assert state.resolve_collection_ids(("chapter 4",)) == recollected.collection_ids
    assert state.resolve_tag_ids(("does-not-exist",)) is None
    assert state.resolve_collection_ids(("does-not-exist",)) is None
    assert state.current_sequence() == 5
    assert [change.sequence_id for change in state.changes_after(2, limit=10)] == [
        3,
        4,
        5,
    ]

    state.delete_note("note-1")

    assert state.note("note-1") is None
    assert state.current_sequence() == 6
    assert state.changes_after(5, limit=10) == (ResearchStateChange(6, "note-1"),)
    assert tuple(record.note_id for record in state.projection_snapshot().records) == (
        "note-2",
    )


def test_sqlite_duplicate_create_rolls_back_user_state_and_journal(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Original", note_id="note-1")

    with pytest.raises(ResearchStateError, match="database operation failed"):
        state.create_note(_anchor(), "Replacement", note_id="note-1")

    assert state.note("note-1") == original
    assert state.current_sequence() == 1
    assert state.changes_after(0, limit=10) == (ResearchStateChange(1, "note-1"),)


def test_sqlite_compaction_retains_requested_tail_and_refuses_future_state(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    state.create_note(_anchor(), "v1", note_id="note-1")
    state.update_note("note-1", "v2")
    state.update_note("note-1", "v3")
    state.update_note("note-1", "v4")

    state.compact_changes(4, retain=2)

    assert state.oldest_change_sequence() == 3
    assert [change.sequence_id for change in state.changes_after(0, limit=10)] == [3, 4]

    with pytest.raises(ResearchStateError, match="beyond authoritative"):
        state.compact_changes(5, retain=0)
    assert [change.sequence_id for change in state.changes_after(0, limit=10)] == [3, 4]


def test_sqlite_rejects_invalid_public_inputs_without_advancing_sequence(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)

    invalid_creates = (
        ("", (), (), "note-a"),
        ("\x00bad", (), (), "note-b"),
        ("valid", ("",), (), "note-c"),
        ("valid", ("bad\nlabel",), (), "note-d"),
        ("valid", (), ("",), "note-e"),
        ("valid", (), (), "bad\nnote"),
    )
    for body, tags, collections, note_id in invalid_creates:
        with pytest.raises(ValueError):
            state.create_note(
                _anchor(),
                body,
                tags=tags,
                collections=collections,
                note_id=note_id,
            )

    assert state.current_sequence() == 0
    assert state.projection_snapshot() == ResearchProjectionSnapshot(0, ())

    with pytest.raises(ValueError, match="limit"):
        state.notes(limit=0)
    with pytest.raises(ValueError, match="document_id"):
        state.notes(document_id=" ")
    with pytest.raises(ValueError, match="duplicate"):
        state.notes_by_ids(("note-1", "note-1"))
    with pytest.raises(ValueError, match="sequence_id"):
        state.changes_after(-1, limit=10)
    with pytest.raises(ValueError, match="batch limit"):
        state.changes_after(0, limit=0)
    with pytest.raises(ValueError, match="through_sequence"):
        state.compact_changes(-1, retain=0)
    with pytest.raises(ValueError, match="retain"):
        state.compact_changes(0, retain=-1)


def test_sqlite_missing_note_mutations_fail_without_journaling(tmp_path: Path) -> None:
    state = _state(tmp_path)

    for operation in (
        lambda: state.update_note("missing", "body"),
        lambda: state.delete_note("missing"),
        lambda: state.set_note_tags("missing", ("tag",)),
        lambda: state.set_note_collections("missing", ("collection",)),
    ):
        with pytest.raises(ResearchStateError, match="does not exist"):
            operation()

    assert state.current_sequence() == 0
    assert state.oldest_change_sequence() is None


def test_sqlite_detects_unsupported_schema_and_corrupt_database(tmp_path: Path) -> None:
    path = tmp_path / "state" / "research.sqlite3"
    state = _state(tmp_path)
    assert state.current_sequence() == 0

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE metadata SET schema_version = 999 WHERE singleton = 1"
        )
        connection.commit()

    with pytest.raises(ResearchStateError, match="schema is unsupported"):
        SqliteResearchStateStore(path, PrivateDirectoryStore())  # type: ignore[arg-type]

    corrupt_path = tmp_path / "corrupt" / "research.sqlite3"
    corrupt_path.parent.mkdir()
    corrupt_path.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(ResearchStateError, match="database operation failed"):
        SqliteResearchStateStore(
            corrupt_path,
            PrivateDirectoryStore(),  # type: ignore[arg-type]
        )


def test_duckdb_projection_composes_filters_summaries_and_deletion(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)
    note_1 = state.create_note(
        _anchor(segment_ids=("segment-000041", "segment-000042")),
        "Housing affordability methodology",
        tags=("housing", "methodology"),
        collections=("Chapter 3",),
        note_id="note-1",
    )
    note_2 = state.create_note(
        _anchor(document_id="job-2", canonical_digit="2"),
        "Housing policy follow up",
        tags=("housing",),
        collections=("Appendix",),
        note_id="note-2",
    )
    snapshot = state.projection_snapshot()
    projection.rebuild(snapshot.records, through_sequence=snapshot.sequence_id)

    housing = state.resolve_tag_ids(("housing",))
    methodology = state.resolve_tag_ids(("methodology",))
    chapter = state.resolve_collection_ids(("Chapter 3",))
    assert housing is not None and methodology is not None and chapter is not None

    assert projection.backend_id == "duckdb-research-projection-v1"
    assert projection.projected_through_sequence() == 2
    assert projection.matching_note_ids(ResearchProjectionFilter(tag_ids=housing)) == (
        "note-1",
        "note-2",
    )
    assert projection.matching_note_ids(
        ResearchProjectionFilter(tag_ids=tuple(sorted(housing + methodology)))
    ) == ("note-1",)
    assert projection.matching_note_ids(
        ResearchProjectionFilter(
            collection_ids=chapter,
            document_ids=("job-1",),
            note_text="AFFORDABILITY methodology",
            require_notes=True,
        )
    ) == ("note-1",)
    assert (
        projection.matching_note_ids(
            ResearchProjectionFilter(document_ids=("job-2",), note_text="methodology")
        )
        == ()
    )
    assert projection.matching_note_ids(ResearchProjectionFilter(note_text="!!!")) == ()

    keys = (
        ("job-1", "1" * 64, "segment-000041"),
        ("job-1", "1" * 64, "segment-000042"),
        ("job-2", "2" * 64, "segment-000042"),
    )
    summaries = projection.summaries(keys + (keys[0],))
    assert summaries[keys[0]].note_ids == (note_1.note_id,)
    assert summaries[keys[0]].tag_ids == note_1.tag_ids
    assert summaries[keys[0]].collection_ids == note_1.collection_ids
    assert summaries[keys[2]].note_ids == (note_2.note_id,)
    assert projection.summaries(()) == {}

    projection.apply((), deleted_note_ids=("note-1",), through_sequence=3)

    assert projection.projected_through_sequence() == 3
    assert projection.matching_note_ids(ResearchProjectionFilter(tag_ids=housing)) == (
        "note-2",
    )
    assert keys[0] not in projection.summaries(keys)


def test_duckdb_projection_transactions_preserve_previous_state_on_invalid_batch(
    tmp_path: Path,
) -> None:
    projection = _projection(tmp_path)
    record = ResearchProjectionRecord(
        note_id="note-1",
        body="durable body",
        anchor=_anchor(),
        tag_ids=(),
        collection_ids=(),
    )
    projection.rebuild((record,), through_sequence=4)

    with pytest.raises(ResearchProjectionError, match="backwards"):
        projection.apply((), deleted_note_ids=(), through_sequence=3)
    with pytest.raises(ValueError, match="duplicate note identities"):
        projection.apply((record,), deleted_note_ids=("note-1",), through_sequence=5)
    with pytest.raises(ValueError, match="negative"):
        projection.rebuild((record,), through_sequence=-1)

    duplicate = ResearchProjectionRecord(
        note_id="note-1",
        body="different body",
        anchor=_anchor(canonical_digit="2"),
        tag_ids=(),
        collection_ids=(),
    )
    with pytest.raises(ResearchProjectionError, match="rebuilt safely"):
        projection.rebuild((record, duplicate), through_sequence=5)

    assert projection.projected_through_sequence() == 4
    assert projection.matching_note_ids(
        ResearchProjectionFilter(require_notes=True)
    ) == ("note-1",)


def test_duckdb_projection_clear_close_and_schema_guards(tmp_path: Path) -> None:
    path = tmp_path / "projection" / "research.duckdb"
    projection = _projection(tmp_path)
    record = ResearchProjectionRecord(
        note_id="note-1",
        body="body",
        anchor=_anchor(),
        tag_ids=(),
        collection_ids=(),
    )
    projection.rebuild((record,), through_sequence=1)

    projection.clear()
    assert projection.projected_through_sequence() == 0
    assert (
        projection.matching_note_ids(ResearchProjectionFilter(require_notes=True)) == ()
    )
    projection.close()
    projection.close()
    with pytest.raises(ResearchProjectionError, match="closed"):
        projection.projected_through_sequence()

    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "UPDATE projection_metadata SET schema_version = 999 WHERE singleton = 1"
        )
    with pytest.raises(ResearchProjectionError, match="schema is unsupported"):
        DuckDbResearchProjection(
            path,
            PrivateDirectoryStore(),  # type: ignore[arg-type]
        )


def test_projector_batches_to_convergence_compacts_and_then_noops(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)
    state.create_note(_anchor(), "one", note_id="note-1")
    state.create_note(_anchor(segment_ids=("segment-000043",)), "two", note_id="note-2")
    state.update_note("note-1", "one revised")
    projector = ResearchStateProjector(
        state,
        projection,
        batch_size=1,
        retained_changes=1,
    )

    status_before = projector.status()
    report = projector.sync()
    status_after = projector.status()
    no_op = projector.sync()

    assert status_before == ResearchProjectionStatus(3, 0)
    assert report.before_sequence == 0
    assert report.after_sequence == 3
    assert report.authoritative_sequence == 3
    assert report.batches == 3
    assert report.current
    assert not report.rebuilt
    assert status_after.current
    assert state.oldest_change_sequence() == 3
    assert no_op.batches == 0
    assert no_op.before_sequence == no_op.after_sequence == 3


def test_projector_rebuilds_snapshot_when_retained_journal_cannot_bridge_gap(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    projection = _projection(tmp_path)
    state.create_note(_anchor(), "one", note_id="note-1")
    state.update_note("note-1", "two")
    state.update_note("note-1", "three")
    state.compact_changes(3, retain=1)
    assert state.oldest_change_sequence() == 3

    report = ResearchStateProjector(state, projection).sync()

    assert report.rebuilt
    assert report.before_sequence == 0
    assert report.after_sequence == 3
    assert projection.matching_note_ids(
        ResearchProjectionFilter(note_text="three")
    ) == ("note-1",)
    assert projection.matching_note_ids(ResearchProjectionFilter(note_text="two")) == ()


def test_research_contract_dataclasses_reject_invalid_state() -> None:
    anchor = _anchor()
    valid_note = dict(
        note_id="note-1",
        body="body",
        anchor=anchor,
        tag_ids=("tag-1",),
        collection_ids=("collection-1",),
        created_at="2026-08-18T12:00:00+00:00",
        updated_at="2026-08-18T12:00:00+00:00",
    )

    with pytest.raises(ValueError, match="note_id"):
        ResearchNote(**{**valid_note, "note_id": " "})
    with pytest.raises(ValueError, match="body"):
        ResearchNote(**{**valid_note, "body": " "})
    with pytest.raises(ValueError, match="tag IDs"):
        ResearchNote(**{**valid_note, "tag_ids": ("tag-2", "tag-1")})
    with pytest.raises(ValueError, match="collection IDs"):
        ResearchNote(
            **{**valid_note, "collection_ids": ("collection-1", "collection-1")}
        )
    with pytest.raises(ValueError, match="timestamps"):
        ResearchNote(**{**valid_note, "created_at": ""})
    with pytest.raises(ValueError, match="tag identity"):
        ResearchTag("", "name")
    with pytest.raises(ValueError, match="collection identity"):
        ResearchCollection("collection-1", "")
    with pytest.raises(ValueError, match="positive"):
        ResearchStateChange(0, "note-1")
    with pytest.raises(ValueError, match="note ID"):
        ResearchStateChange(1, "")
    with pytest.raises(ValueError, match="identity and body"):
        ResearchProjectionRecord("", "body", anchor, (), ())
    with pytest.raises(ValueError, match="tag IDs"):
        ResearchProjectionRecord("note", "body", anchor, ("z", "a"), ())
    with pytest.raises(ValueError, match="collection IDs"):
        ResearchProjectionRecord("note", "body", anchor, (), ("x", "x"))
    with pytest.raises(ValueError, match="negative"):
        ResearchProjectionSnapshot(-1, ())


def test_projection_contracts_validate_filter_shape_and_status() -> None:
    assert not ResearchProjectionFilter().active
    assert ResearchProjectionFilter(require_notes=True).active
    assert ProjectedEvidenceSummary(note_ids=("a", "b")).note_count == 2
    assert ResearchProjectionStatus(4, 4).current
    assert not ResearchProjectionStatus(4, 3).current

    for kwargs in (
        {"tag_ids": ("",)},
        {"tag_ids": ("z", "a")},
        {"collection_ids": ("x", "x")},
        {"document_ids": ("",)},
        {"note_text": " "},
    ):
        with pytest.raises(ValueError):
            ResearchProjectionFilter(**kwargs)
    with pytest.raises(ValueError, match="negative"):
        ResearchProjectionStatus(-1, 0)
