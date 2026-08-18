from pathlib import Path

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.duckdb_semantic import DuckDbSemanticIndex
from echoflow.library.index import IndexedSegment, IndexedTranscript, SearchQuery
from echoflow.library.semantic import EmbeddingProfile, SearchChunk, SemanticState


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _transcript(document_id: str, canonical_digit: str) -> IndexedTranscript:
    return IndexedTranscript(
        document_id=document_id,
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=f"/{document_id}.json",
        source_path=f"/{document_id}.wav",
        source_size_bytes=100,
        source_modified_ns=1,
        segments=(
            IndexedSegment(
                segment_id="segment-000001",
                start_seconds=1.0,
                end_seconds=2.0,
                text="housing affordability evidence",
                language="en",
            ),
        ),
    )


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="profile",
        provider="test",
        model_id="test-model",
        resolved_revision="revision",
        dimensions=2,
        normalization="l2",
        pooling="mean",
        distance_metric="dot",
        query_prefix="query: ",
        passage_prefix="passage: ",
        chunking_profile_id="search-chunk-v1",
        snapshot_path="/private/model",
    )


def _chunk(document_id: str, canonical_digit: str) -> SearchChunk:
    return SearchChunk(
        chunk_id=f"chunk-{document_id}",
        document_id=document_id,
        source_sha256="0" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/{document_id}.json",
        source_path=f"/{document_id}.wav",
        segment_ids=("segment-000001",),
        first_segment_id="segment-000001",
        last_segment_id="segment-000001",
        start_seconds=1.0,
        end_seconds=2.0,
        text="housing affordability evidence",
        content_sha256=("a" if document_id == "job-1" else "b") * 64,
        chunking_profile_id="search-chunk-v1",
        languages=("en",),
    )


def test_lexical_scope_filters_before_ranking_and_empty_scope_matches_nothing(
    tmp_path: Path,
) -> None:
    store = PrivateDirectoryStore()
    index = DuckDbTranscriptIndex(
        tmp_path / "lexical.duckdb",
        store,  # type: ignore[arg-type]
    )
    index.rebuild((_transcript("job-1", "1"), _transcript("job-2", "2")))

    unrestricted = index.search(SearchQuery("housing"))
    scoped = index.search(
        SearchQuery(
            "housing",
            evidence_scope=(("job-2", "2" * 64, "segment-000001"),),
        )
    )
    empty = index.search(SearchQuery("housing", evidence_scope=()))

    assert {item.document_id for item in unrestricted} == {"job-1", "job-2"}
    assert [item.document_id for item in scoped] == ["job-2"]
    assert empty == ()


def test_semantic_scope_filters_before_vector_scoring_and_chunk_lookup_is_targeted(
    tmp_path: Path,
) -> None:
    store = PrivateDirectoryStore()
    index = DuckDbSemanticIndex(
        tmp_path / "semantic.duckdb",
        store,  # type: ignore[arg-type]
    )
    chunks = (_chunk("job-1", "1"), _chunk("job-2", "2"))
    index.rebuild(
        state=SemanticState(_profile(), "f" * 64, 2),
        chunks=chunks,
        vectors=((1.0, 0.0), (0.0, 1.0)),
    )

    scoped = index.search(
        SearchQuery(
            "housing",
            evidence_scope=(("job-2", "2" * 64, "segment-000001"),),
        ),
        (1.0, 0.0),
    )
    empty = index.search(
        SearchQuery("housing", evidence_scope=()),
        (1.0, 0.0),
    )
    located = index.chunks_for_segments((("job-2", "segment-000001"),))

    assert [candidate.chunk.document_id for candidate in scoped] == ["job-2"]
    assert empty == ()
    assert located[("job-2", "segment-000001")].chunk_id == "chunk-job-2"
