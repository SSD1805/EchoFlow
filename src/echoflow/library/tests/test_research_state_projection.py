from pathlib import Path

import pytest

from echoflow.library.duckdb_research_projection import DuckDbResearchProjection
from echoflow.library.errors import ResearchProjectionError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_projection import ResearchProjectionFilter
from echoflow.library.research_projector import ResearchStateProjector
from echoflow.library.sqlite_research_state import SqliteResearchStateStore


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _anchor(
    canonical_digit: str = "1",
    *,
    segment_id: str = "segment-000042",
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path="/private/interview.json",
        source_path="/private/interview.wav",
        segment_ids=(segment_id,),
        start_seconds=42.0,
        end_seconds=45.0,
    )


def _stores(tmp_path: Path):
    file_store = PrivateDirectoryStore()
    state = SqliteResearchStateStore(
        tmp_path / "user-state" / "research.sqlite3",
        file_store,  # type: ignore[arg-type]
    )
    projection = DuckDbResearchProjection(
        tmp_path / "projections" / "research.duckdb",
        file_store,  # type: ignore[arg-type]
    )
    return state, projection


def test_sqlite_state_commits_note_labels_and_outbox_together(tmp_path: Path) -> None:
    state, _ = _stores(tmp_path)

    note = state.create_note(
        _anchor(),
        "Check this against the 2024 survey.",
        tags=("Methodology", "housing"),
        collections=("Chapter 3",),
        note_id="note-1",
    )

    assert state.current_sequence() == 1
    assert len(note.tag_ids) == 2
    assert len(note.collection_ids) == 1
    assert state.note("note-1") == note
    snapshot = state.projection_snapshot()
    assert snapshot.sequence_id == 1
    assert snapshot.records[0].note_id == "note-1"
    assert snapshot.records[0].anchor.canonical_sha256 == "1" * 64
    assert state.changes_after(0, limit=10)[0].note_id == "note-1"


def test_projection_replays_incremental_mutations_and_note_terms(
    tmp_path: Path,
) -> None:
    state, projection = _stores(tmp_path)
    state.create_note(
        _anchor(),
        "Housing affordability methodology needs checking",
        tags=("methodology",),
        note_id="note-1",
    )
    projector = ResearchStateProjector(state, projection, batch_size=1)

    first = projector.sync()

    tag_id = state.resolve_tag_ids(("methodology",))
    assert tag_id is not None
    assert first.current
    assert first.batches == 1
    assert projection.matching_evidence(ResearchProjectionFilter(tag_ids=tag_id)) == (
        ("job-1", "1" * 64, "segment-000042"),
    )
    assert projection.matching_evidence(
        ResearchProjectionFilter(note_text="affordability checking")
    ) == (("job-1", "1" * 64, "segment-000042"),)

    state.update_note("note-1", "A completely different observation")
    second = projector.sync()

    assert second.current
    assert (
        projection.matching_evidence(
            ResearchProjectionFilter(note_text="affordability")
        )
        == ()
    )
    assert projection.matching_evidence(
        ResearchProjectionFilter(note_text="different observation")
    ) == (("job-1", "1" * 64, "segment-000042"),)


def test_projection_keeps_canonical_generations_separate(tmp_path: Path) -> None:
    state, projection = _stores(tmp_path)
    state.create_note(
        _anchor("1"),
        "Old generation note",
        tags=("history",),
        note_id="old-note",
    )
    state.create_note(
        _anchor("2"),
        "Current generation note",
        tags=("current",),
        note_id="current-note",
    )
    projector = ResearchStateProjector(state, projection)
    projector.sync()

    history = state.resolve_tag_ids(("history",))
    current = state.resolve_tag_ids(("current",))
    assert history is not None and current is not None
    assert projection.matching_evidence(ResearchProjectionFilter(tag_ids=history)) == (
        ("job-1", "1" * 64, "segment-000042"),
    )
    assert projection.matching_evidence(ResearchProjectionFilter(tag_ids=current)) == (
        ("job-1", "2" * 64, "segment-000042"),
    )


def test_deleted_projection_rebuilds_from_sqlite_after_outbox_compaction(
    tmp_path: Path,
) -> None:
    state, projection = _stores(tmp_path)
    state.create_note(_anchor(), "Durable note", note_id="note-1")
    projector = ResearchStateProjector(state, projection, retained_changes=0)
    projector.sync()
    assert state.oldest_change_sequence() is None
    projection.clear()

    report = projector.sync()

    assert report.rebuilt
    assert report.current
    key = ("job-1", "1" * 64, "segment-000042")
    assert projection.summaries((key,))[key].note_ids == ("note-1",)


def test_projection_ahead_of_authoritative_state_fails_closed(tmp_path: Path) -> None:
    state, projection = _stores(tmp_path)
    projection.rebuild((), through_sequence=7)
    projector = ResearchStateProjector(state, projection)

    with pytest.raises(ResearchProjectionError, match="ahead"):
        projector.sync()
