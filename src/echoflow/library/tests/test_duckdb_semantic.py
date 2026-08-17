from pathlib import Path

import pytest

from echoflow.library.duckdb_semantic import DuckDbSemanticIndex
from echoflow.library.index import IndexedSegment, IndexedTranscript, SearchQuery
from echoflow.library.semantic import (
    ChunkingProfile,
    EmbeddingProfile,
    SemanticState,
    build_search_chunks,
)


class DirectoryManager:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _vector(axis: int) -> tuple[float, ...]:
    values = [0.0] * 384
    values[axis] = 1.0
    return tuple(values)


def _profile(tmp_path: Path) -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="profile-1",
        provider="test",
        model_id="test/model",
        resolved_revision="revision",
        dimensions=384,
        normalization="l2",
        pooling="mean",
        distance_metric="dot",
        query_prefix="query: ",
        passage_prefix="passage: ",
        chunking_profile_id="tiny-test",
        snapshot_path=str(tmp_path / "revision"),
    )


def _transcript(tmp_path: Path) -> IndexedTranscript:
    return IndexedTranscript(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=str(tmp_path / "job-1.json"),
        source_path=str(tmp_path / "job-1.wav"),
        source_size_bytes=10,
        source_modified_ns=1,
        segments=(
            IndexedSegment("s1", 0, 1, "housing affordability", "en", "speaker-01"),
            IndexedSegment("s2", 1, 2, "rent burden pressure", "en", "speaker-02"),
        ),
    )


def _index(tmp_path: Path) -> DuckDbSemanticIndex:
    return DuckDbSemanticIndex(
        tmp_path / "private" / "semantic.duckdb",
        DirectoryManager(),  # type: ignore[arg-type]
    )


def test_exact_vectors_round_trip_as_numeric_arrays_and_rank_locally(
    tmp_path: Path,
) -> None:
    chunks = build_search_chunks(
        (_transcript(tmp_path),),
        profile=ChunkingProfile("tiny-test", target_words=2, max_words=2),
    )
    profile = _profile(tmp_path)
    state = SemanticState(profile, "a" * 64, len(chunks))
    index = _index(tmp_path)

    index.rebuild(state=state, chunks=chunks, vectors=(_vector(0), _vector(1)))

    assert index.backend_id == "duckdb-exact-vector-v1"
    assert index.state() == state
    matches = index.search(SearchQuery("concept", limit=2), _vector(1))
    assert [candidate.chunk.segment_ids for candidate in matches] == [("s2",), ("s1",)]
    assert matches[0].score == pytest.approx(1.0)
    assert matches[1].score == pytest.approx(0.0)

    stored_type = index._connection.execute(  # noqa: SLF001
        "SELECT typeof(vector) FROM embeddings LIMIT 1"
    ).fetchone()
    assert stored_type is not None
    assert stored_type[0] in {"FLOAT[]", "FLOAT[384]"}
    index.close()


def test_metadata_filtering_happens_before_top_k_semantic_ranking(
    tmp_path: Path,
) -> None:
    chunks = build_search_chunks(
        (_transcript(tmp_path),),
        profile=ChunkingProfile("tiny-test", target_words=2, max_words=2),
    )
    profile = _profile(tmp_path)
    index = _index(tmp_path)
    index.rebuild(
        state=SemanticState(profile, "a" * 64, len(chunks)),
        chunks=chunks,
        vectors=(_vector(0), _vector(1)),
    )

    matches = index.search(
        SearchQuery(
            "rent",
            speaker_refs=("speaker-02",),
            languages=("en",),
            limit=1,
        ),
        _vector(0),
    )

    assert len(matches) == 1
    assert matches[0].chunk.segment_ids == ("s2",)
    assert matches[0].score == pytest.approx(0.0)
    index.close()


def test_phrase_and_all_terms_remain_hard_constraints_in_semantic_mode(
    tmp_path: Path,
) -> None:
    chunks = build_search_chunks(
        (_transcript(tmp_path),),
        profile=ChunkingProfile("tiny-test", target_words=2, max_words=2),
    )
    profile = _profile(tmp_path)
    index = _index(tmp_path)
    index.rebuild(
        state=SemanticState(profile, "a" * 64, len(chunks)),
        chunks=chunks,
        vectors=(_vector(0), _vector(1)),
    )

    phrase = index.search(
        SearchQuery("housing affordability", phrase=True),
        _vector(0),
    )
    missing_phrase = index.search(
        SearchQuery("affordability housing", phrase=True),
        _vector(0),
    )

    assert [item.chunk.segment_ids for item in phrase] == [("s1",)]
    assert missing_phrase == ()
    index.close()


def test_segment_resolution_anchors_lexical_hits_to_derived_chunks(
    tmp_path: Path,
) -> None:
    chunks = build_search_chunks(
        (_transcript(tmp_path),),
        profile=ChunkingProfile("tiny-test", target_words=10, max_words=10),
    )
    profile = _profile(tmp_path)
    index = _index(tmp_path)
    index.rebuild(
        state=SemanticState(profile, "a" * 64, len(chunks)),
        chunks=chunks,
        vectors=(_vector(0),),
    )

    resolved = index.chunks_for_segments((("job-1", "s2"), ("job-1", "missing")))

    assert resolved[("job-1", "s2")].segment_ids == ("s1", "s2")
    assert ("job-1", "missing") not in resolved
    index.close()


def test_invalid_rebuild_is_rejected_before_destroying_previous_state(
    tmp_path: Path,
) -> None:
    chunks = build_search_chunks(
        (_transcript(tmp_path),),
        profile=ChunkingProfile("tiny-test", target_words=10, max_words=10),
    )
    profile = _profile(tmp_path)
    state = SemanticState(profile, "a" * 64, 1)
    index = _index(tmp_path)
    index.rebuild(state=state, chunks=chunks, vectors=(_vector(0),))

    with pytest.raises(ValueError, match="dimensions"):
        index.rebuild(
            state=state,
            chunks=chunks,
            vectors=((1.0,),),
        )

    assert index.state() == state
    index.close()
