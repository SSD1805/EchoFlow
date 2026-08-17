from pathlib import Path

import pytest

from echoflow.library.duckdb_index import DuckDbTranscriptIndex, lexical_tokens
from echoflow.library.index import (
    IndexedSegment,
    IndexedTranscript,
    SearchOperator,
    SearchQuery,
    SearchSort,
)


class DirectoryManager:
    def __init__(self) -> None:
        self.private_directories: list[Path] = []

    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
        self.private_directories.append(path)


def _transcript(
    tmp_path: Path,
    document_id: str,
    *,
    segments: tuple[IndexedSegment, ...],
    digest_char: str = "0",
) -> IndexedTranscript:
    return IndexedTranscript(
        document_id=document_id,
        source_sha256=digest_char * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=str(tmp_path / f"{document_id}.json"),
        source_path=str(tmp_path / f"{document_id}.wav"),
        source_size_bytes=123,
        source_modified_ns=7,
        segments=segments,
    )


def _index(tmp_path: Path) -> tuple[DuckDbTranscriptIndex, DirectoryManager]:
    manager = DirectoryManager()
    return DuckDbTranscriptIndex(tmp_path / "private" / "library.duckdb", manager), manager  # type: ignore[arg-type]


def test_lexical_tokens_are_casefolded_unicode_aware_and_repeatable() -> None:
    assert lexical_tokens("Housing HOUSING l’été O'Brien") == (
        "housing",
        "housing",
        "l’été",
        "o'brien",
    )


def test_rebuild_indexes_documents_and_bm25_ranks_term_frequency(tmp_path: Path) -> None:
    index, manager = _index(tmp_path)
    transcript = _transcript(
        tmp_path,
        "job-1",
        segments=(
            IndexedSegment(
                "segment-000000",
                0,
                1,
                "housing housing housing prices affordability",
                "en",
                "speaker-01",
            ),
            IndexedSegment(
                "segment-000001",
                1,
                2,
                "housing affordability",
                "en",
                "speaker-02",
            ),
            IndexedSegment(
                "segment-000002",
                2,
                3,
                "transit affordability",
                "en",
                None,
            ),
        ),
    )

    index.rebuild((transcript,))
    matches = index.search(SearchQuery("housing"))

    assert manager.private_directories == [tmp_path / "private"]
    assert index.backend_id == "duckdb-bm25-v1"
    assert index.contains("job-1") is True
    assert matches[0].segment_id == "segment-000000"
    assert matches[0].score > matches[1].score > 0
    assert matches[0].source_sha256 == "0" * 64
    assert matches[0].canonical_path.endswith("job-1.json")
    assert index.documents()[0].segment_count == 3
    index.close()


def test_any_all_phrase_and_metadata_filters_share_one_query_contract(
    tmp_path: Path,
) -> None:
    index, _ = _index(tmp_path)
    index.rebuild(
        (
            _transcript(
                tmp_path,
                "job-a",
                segments=(
                    IndexedSegment(
                        "segment-000000",
                        0,
                        1,
                        "housing prices affordability",
                        "en",
                        "speaker-01",
                    ),
                    IndexedSegment(
                        "segment-000001",
                        1,
                        2,
                        "housing affordability improves",
                        "fr",
                        "speaker-02",
                    ),
                ),
            ),
            _transcript(
                tmp_path,
                "job-b",
                digest_char="1",
                segments=(
                    IndexedSegment(
                        "segment-000000",
                        0,
                        1,
                        "housing policy",
                        "en",
                        "speaker-02",
                    ),
                ),
            ),
        )
    )

    any_matches = index.search(SearchQuery("housing affordability"))
    all_matches = index.search(
        SearchQuery("housing affordability", operator=SearchOperator.ALL)
    )
    phrase_matches = index.search(SearchQuery("housing affordability", phrase=True))
    filtered = index.search(
        SearchQuery(
            "housing",
            speaker_refs=("speaker-02",),
            languages=("en",),
            document_ids=("job-b",),
        )
    )

    assert len(any_matches) == 3
    assert {match.segment_id for match in all_matches} == {
        "segment-000000",
        "segment-000001",
    }
    assert [(match.document_id, match.segment_id) for match in phrase_matches] == [
        ("job-a", "segment-000001")
    ]
    assert [(match.document_id, match.speaker_ref) for match in filtered] == [
        ("job-b", "speaker-02")
    ]
    index.close()


def test_timeline_sort_limit_upsert_remove_and_clear(tmp_path: Path) -> None:
    index, _ = _index(tmp_path)
    first = _transcript(
        tmp_path,
        "job-a",
        segments=(
            IndexedSegment("segment-000000", 5, 6, "housing later"),
            IndexedSegment("segment-000001", 1, 2, "housing earlier"),
        ),
    )
    index.rebuild((first,))

    timeline = index.search(
        SearchQuery("housing", sort=SearchSort.TIMELINE, limit=1)
    )
    assert [match.segment_id for match in timeline] == ["segment-000001"]

    replacement = _transcript(
        tmp_path,
        "job-a",
        segments=(IndexedSegment("segment-000000", 0, 1, "replacement housing"),),
    )
    index.upsert(replacement)
    assert index.documents()[0].segment_count == 1
    assert index.search(SearchQuery("earlier")) == ()

    index.remove("missing")
    index.remove("job-a")
    assert index.contains("job-a") is False
    index.rebuild((replacement,))
    index.clear()
    assert index.documents() == ()
    index.close()
    index.close()
    with pytest.raises(RuntimeError, match="closed"):
        index.documents()


def test_rebuild_rolls_back_to_previous_index_on_duplicate_document_failure(
    tmp_path: Path,
) -> None:
    index, _ = _index(tmp_path)
    original = _transcript(
        tmp_path,
        "original",
        segments=(IndexedSegment("segment-000000", 0, 1, "original evidence"),),
    )
    index.rebuild((original,))
    duplicate_a = _transcript(
        tmp_path,
        "duplicate",
        segments=(IndexedSegment("segment-000000", 0, 1, "first duplicate"),),
    )
    duplicate_b = _transcript(
        tmp_path,
        "duplicate",
        segments=(IndexedSegment("segment-000001", 1, 2, "second duplicate"),),
    )

    with pytest.raises(Exception):
        index.rebuild((duplicate_a, duplicate_b))

    assert [item.document_id for item in index.documents()] == ["original"]
    assert index.search(SearchQuery("original"))[0].text == "original evidence"
    index.close()


def test_search_rejects_punctuation_only_query(tmp_path: Path) -> None:
    index, _ = _index(tmp_path)
    with pytest.raises(ValueError, match="searchable token"):
        index.search(SearchQuery("---"))
    index.close()
