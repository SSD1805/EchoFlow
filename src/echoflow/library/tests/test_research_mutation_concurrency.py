from pathlib import Path

import pytest

from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.sqlite_research_state import SqliteResearchStateStore


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _state(tmp_path: Path) -> SqliteResearchStateStore:
    return SqliteResearchStateStore(
        tmp_path / "research.sqlite3",
        PrivateDirectoryStore(),  # type: ignore[arg-type]
    )


def _anchor() -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="interview-42",
        source_sha256="b" * 64,
        canonical_sha256="a" * 64,
        canonical_path="/private/interview-42.json",
        source_path="/private/interview-42.wav",
        segment_ids=("segment-17",),
        start_seconds=862.1,
        end_seconds=870.4,
    )


def test_replace_note_is_one_version_checked_authoritative_mutation(tmp_path: Path) -> None:
    state = _state(tmp_path)
    original = state.create_note(
        _anchor(),
        "Initial interpretation",
        tags=("program",),
        collections=("Oral histories",),
        note_id="note-7",
    )

    updated = state.replace_note(
        "note-7",
        "Compare this passage with the follow-up interview.",
        tags=("program", "follow-up"),
        collections=("Oral histories", "Chapter 3"),
        expected_updated_at=original.updated_at,
    )

    assert updated.anchor == original.anchor
    assert updated.body == "Compare this passage with the follow-up interview."
    assert {tag.name for tag in state.tags() if tag.tag_id in updated.tag_ids} == {
        "program",
        "follow-up",
    }
    assert {
        collection.name
        for collection in state.collections()
        if collection.collection_id in updated.collection_ids
    } == {"Oral histories", "Chapter 3"}
    assert state.current_sequence() == 2
    assert [change.sequence_id for change in state.changes_after(1, limit=10)] == [2]


def test_stale_replace_and_delete_fail_closed_without_advancing_state(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    original = state.create_note(_anchor(), "Version one", note_id="note-7")
    current = state.replace_note(
        "note-7",
        "Version two",
        tags=(),
        collections=(),
        expected_updated_at=original.updated_at,
    )
    sequence = state.current_sequence()

    with pytest.raises(ResearchStateError, match="changed since it was opened"):
        state.replace_note(
            "note-7",
            "Stale overwrite",
            tags=("stale",),
            collections=(),
            expected_updated_at=original.updated_at,
        )
    with pytest.raises(ResearchStateError, match="changed since it was opened"):
        state.delete_note("note-7", expected_updated_at=original.updated_at)

    assert state.note("note-7") == current
    assert state.current_sequence() == sequence

    state.delete_note("note-7", expected_updated_at=current.updated_at)
    assert state.note("note-7") is None
    assert state.current_sequence() == sequence + 1
