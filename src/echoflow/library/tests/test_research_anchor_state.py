import sqlite3
from pathlib import Path

import pytest

from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.sqlite_research_anchor_state import SqliteResearchAnchorStateStore
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
    source_digit: str = "a",
    canonical_digit: str = "b",
    segment_ids: tuple[str, ...] = ("segment-1",),
    start_seconds: float = 2.0,
    end_seconds: float = 3.0,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id=document_id,
        source_sha256=source_digit * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/private/{document_id}-{canonical_digit}.json",
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


def test_reanchor_preserves_prior_anchor_and_advances_projection_once(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(
        _anchor(),
        "Interpretation",
        tags=("review",),
        collections=("Chapter 1",),
        note_id="note-1",
    )
    anchor_state = SqliteResearchAnchorStateStore(state.database_path)
    replacement = _anchor(
        canonical_digit="c",
        segment_ids=("segment-current-1", "segment-current-2"),
        start_seconds=2.1,
        end_seconds=3.2,
    )

    anchor_state.reanchor_note(
        "note-1",
        replacement,
        expected_updated_at=original.updated_at,
    )

    updated = state.note("note-1")
    assert updated is not None
    assert updated.anchor == replacement
    assert updated.body == original.body
    assert updated.tag_ids == original.tag_ids
    assert updated.collection_ids == original.collection_ids
    assert updated.updated_at != original.updated_at
    assert state.current_sequence() == 2
    assert [change.sequence_id for change in state.changes_after(1, limit=10)] == [2]
    assert state.projection_records(("note-1",))[0].anchor == replacement

    history = anchor_state.note_anchor_history("note-1")
    assert len(history) == 1
    assert history[0].revision == 1
    assert history[0].anchor == original.anchor
    assert history[0].replaced_at == updated.updated_at


def test_reanchor_is_optimistic_and_rolls_back_history_on_stale_version(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Interpretation", note_id="note-1")
    newer = state.update_note("note-1", "Changed elsewhere")
    anchor_state = SqliteResearchAnchorStateStore(state.database_path)

    with pytest.raises(ResearchStateError, match="changed since its evidence was reviewed"):
        anchor_state.reanchor_note(
            "note-1",
            _anchor(canonical_digit="c"),
            expected_updated_at=original.updated_at,
        )

    assert state.note("note-1") == newer
    assert state.current_sequence() == 2
    assert anchor_state.note_anchor_history("note-1") == ()


def test_reanchor_refuses_cross_document_or_cross_source_moves(tmp_path: Path) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Interpretation", note_id="note-1")
    anchor_state = SqliteResearchAnchorStateStore(state.database_path)

    with pytest.raises(ResearchStateError, match="different transcript"):
        anchor_state.reanchor_note(
            "note-1",
            _anchor(document_id="job-2", canonical_digit="c"),
            expected_updated_at=original.updated_at,
        )
    with pytest.raises(ResearchStateError, match="different source evidence"):
        anchor_state.reanchor_note(
            "note-1",
            _anchor(source_digit="f", canonical_digit="c"),
            expected_updated_at=original.updated_at,
        )

    assert state.current_sequence() == 1
    assert anchor_state.note_anchor_history("note-1") == ()


def test_reanchor_refuses_noop_and_retains_multiple_history_revisions(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Interpretation", note_id="note-1")
    anchor_state = SqliteResearchAnchorStateStore(state.database_path)

    with pytest.raises(ResearchStateError, match="already cites"):
        anchor_state.reanchor_note(
            "note-1",
            original.anchor,
            expected_updated_at=original.updated_at,
        )

    first = _anchor(canonical_digit="c", segment_ids=("current-1",))
    anchor_state.reanchor_note(
        "note-1", first, expected_updated_at=original.updated_at
    )
    after_first = state.note("note-1")
    assert after_first is not None
    second = _anchor(canonical_digit="d", segment_ids=("current-2",))
    anchor_state.reanchor_note(
        "note-1", second, expected_updated_at=after_first.updated_at
    )

    history = anchor_state.note_anchor_history("note-1")
    assert [entry.revision for entry in history] == [2, 1]
    assert history[0].anchor == first
    assert history[1].anchor == original.anchor
    assert state.current_sequence() == 3


def test_anchor_history_cascades_with_note_and_versions_its_extension(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Interpretation", note_id="note-1")
    anchor_state = SqliteResearchAnchorStateStore(state.database_path)
    anchor_state.reanchor_note(
        "note-1",
        _anchor(canonical_digit="c"),
        expected_updated_at=original.updated_at,
    )
    current = state.note("note-1")
    assert current is not None
    state.delete_note("note-1", expected_updated_at=current.updated_at)

    with pytest.raises(ResearchStateError, match="does not exist"):
        anchor_state.note_anchor_history("note-1")

    with sqlite3.connect(state.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM note_anchor_history").fetchone() == (
            0,
        )
        connection.execute(
            "UPDATE anchor_history_metadata SET schema_version = 99 WHERE singleton = 1"
        )
        connection.commit()

    with pytest.raises(ResearchStateError, match="schema is unsupported"):
        SqliteResearchAnchorStateStore(state.database_path)
