from pathlib import Path

import duckdb
import pytest

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.index import IndexedSegment, IndexedTranscript, SearchQuery


class DirectoryManager:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _transcript(
    tmp_path: Path,
    document_id: str,
    text: str,
    *,
    canonical_char: str,
) -> IndexedTranscript:
    return IndexedTranscript(
        document_id=document_id,
        source_sha256="a" * 64,
        canonical_sha256=canonical_char * 64,
        canonical_size_bytes=100,
        canonical_modified_ns=10,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=str(tmp_path / f"{document_id}.json"),
        source_path=str(tmp_path / f"{document_id}.wav"),
        source_size_bytes=10,
        source_modified_ns=5,
        segments=(IndexedSegment("segment-000000", 0, 1, text),),
    )


def _index(tmp_path: Path) -> DuckDbTranscriptIndex:
    return DuckDbTranscriptIndex(
        tmp_path / "library.duckdb",
        DirectoryManager(),  # type: ignore[arg-type]
    )


def test_apply_delta_commits_upserts_and_removals_together(tmp_path: Path) -> None:
    index = _index(tmp_path)
    first = _transcript(tmp_path, "first", "old first", canonical_char="1")
    second = _transcript(tmp_path, "second", "old second", canonical_char="2")
    index.rebuild((first, second))

    replacement = _transcript(
        tmp_path,
        "second",
        "replacement second",
        canonical_char="3",
    )
    third = _transcript(tmp_path, "third", "new third", canonical_char="4")
    index.apply_delta(upserts=(replacement, third), removals=("first",))

    assert [item.document_id for item in index.documents()] == ["second", "third"]
    assert index.search(SearchQuery("old")) == ()
    assert index.search(SearchQuery("replacement"))[0].document_id == "second"
    assert index.search(SearchQuery("new"))[0].document_id == "third"


def test_apply_delta_rolls_back_entire_refresh_when_one_upsert_fails(
    tmp_path: Path,
) -> None:
    index = _index(tmp_path)
    original = _transcript(
        tmp_path, "original", "original evidence", canonical_char="1"
    )
    index.rebuild((original,))
    valid = _transcript(tmp_path, "valid", "valid evidence", canonical_char="2")
    duplicate_segment = IndexedTranscript(
        document_id="broken",
        source_sha256="a" * 64,
        canonical_sha256="3" * 64,
        canonical_size_bytes=100,
        canonical_modified_ns=10,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=str(tmp_path / "broken.json"),
        source_path=None,
        source_size_bytes=10,
        source_modified_ns=5,
        segments=(
            IndexedSegment("segment-000000", 0, 1, "first"),
            IndexedSegment("segment-000001", 1, 2, "second"),
        ),
    )
    # Force the second insert to fail inside DuckDB after earlier delta work has run.
    index._connection.execute(
        """
        CREATE UNIQUE INDEX force_text_collision
        ON segments(text)
        """
    )
    broken = IndexedTranscript(
        document_id=duplicate_segment.document_id,
        source_sha256=duplicate_segment.source_sha256,
        canonical_sha256=duplicate_segment.canonical_sha256,
        canonical_size_bytes=duplicate_segment.canonical_size_bytes,
        canonical_modified_ns=duplicate_segment.canonical_modified_ns,
        transcript_schema_version=duplicate_segment.transcript_schema_version,
        detected_language=duplicate_segment.detected_language,
        canonical_path=duplicate_segment.canonical_path,
        source_path=duplicate_segment.source_path,
        source_size_bytes=duplicate_segment.source_size_bytes,
        source_modified_ns=duplicate_segment.source_modified_ns,
        segments=(
            IndexedSegment("segment-000000", 0, 1, "collision"),
            IndexedSegment("segment-000001", 1, 2, "collision"),
        ),
    )

    with pytest.raises(duckdb.ConstraintException):
        index.apply_delta(
            upserts=(valid, broken),
            removals=("original",),
        )

    assert [item.document_id for item in index.documents()] == ["original"]
    assert index.search(SearchQuery("original"))[0].document_id == "original"
    assert index.contains("valid") is False
    assert index.contains("broken") is False


@pytest.mark.parametrize(
    ("upserts", "removals", "message"),
    [
        (("duplicate", "duplicate"), (), "duplicate document IDs"),
        ((), ("",), "empty document IDs"),
        ((), ("same", "same"), "duplicate document IDs"),
        (("same",), ("same",), "both upserted and removed"),
    ],
)
def test_apply_delta_rejects_ambiguous_delta_contract(
    tmp_path: Path,
    upserts: tuple[str, ...],
    removals: tuple[str, ...],
    message: str,
) -> None:
    index = _index(tmp_path)
    transcripts = tuple(
        _transcript(tmp_path, item, item, canonical_char=str(position + 1))
        for position, item in enumerate(upserts)
    )
    with pytest.raises(ValueError, match=message):
        index.apply_delta(upserts=transcripts, removals=removals)
