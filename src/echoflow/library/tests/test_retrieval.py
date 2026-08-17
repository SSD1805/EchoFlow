from echoflow.library.index import (
    IndexedDocument,
    SearchQuery,
    SearchSort,
    TranscriptMatch,
)
from echoflow.library.retrieval import RetrievalMode, TranscriptSearch
from echoflow.library.semantic import (
    EmbeddingProfile,
    SearchChunk,
    SemanticCandidate,
    SemanticState,
)


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="profile",
        provider="test",
        model_id="test/model",
        resolved_revision="revision",
        dimensions=3,
        normalization="l2",
        pooling="mean",
        distance_metric="dot",
        query_prefix="query: ",
        passage_prefix="passage: ",
        chunking_profile_id="chunks",
        snapshot_path="/private/revision",
    )


def _chunk(
    chunk_id: str,
    segment_ids: tuple[str, ...],
    *,
    start: float,
    text: str,
) -> SearchChunk:
    digest_char = {"a": "a", "b": "b", "c": "c"}[chunk_id]
    return SearchChunk(
        chunk_id=chunk_id,
        document_id="job",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/canonical.json",
        source_path="/audio.wav",
        segment_ids=segment_ids,
        first_segment_id=segment_ids[0],
        last_segment_id=segment_ids[-1],
        start_seconds=start,
        end_seconds=start + 1,
        text=text,
        content_sha256=digest_char * 64,
        chunking_profile_id="chunks",
        languages=("en",),
        speaker_refs=("speaker-01",),
    )


def _match(segment_id: str, score: float, start: float) -> TranscriptMatch:
    return TranscriptMatch(
        document_id="job",
        source_sha256="0" * 64,
        canonical_path="/canonical.json",
        source_path="/audio.wav",
        segment_id=segment_id,
        start_seconds=start,
        end_seconds=start + 1,
        text=f"lexical {segment_id}",
        language="en",
        speaker_ref="speaker-01",
        score=score,
    )


class Lexical:
    backend_id = "lexical"

    def __init__(self, matches: tuple[TranscriptMatch, ...]) -> None:
        self.matches = matches

    def documents(self) -> tuple[IndexedDocument, ...]:
        return (
            IndexedDocument(
                document_id="job",
                source_sha256="0" * 64,
                detected_language="en",
                canonical_path="/canonical.json",
                source_path="/audio.wav",
                segment_count=3,
                canonical_sha256="1" * 64,
            ),
        )

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]:
        return self.matches[: query.limit]


class Provider:
    profile = _profile()

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        assert texts
        return ((1.0, 0.0, 0.0),)

    def embed_passages(
        self, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        raise AssertionError("search must not re-embed passages")


class Semantic:
    backend_id = "semantic"

    def __init__(
        self,
        chunks: tuple[SearchChunk, ...],
        candidates: tuple[SemanticCandidate, ...],
    ) -> None:
        self.chunks = chunks
        self.candidates = candidates

    def state(self) -> SemanticState:
        return SemanticState(_profile(), "f" * 64, len(self.chunks))

    def search(
        self, query: SearchQuery, query_vector: tuple[float, ...]
    ) -> tuple[SemanticCandidate, ...]:
        assert query_vector == (1.0, 0.0, 0.0)
        return self.candidates[: query.limit]

    def chunks_for_segments(
        self, keys: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], SearchChunk]:
        wanted = set(keys)
        return {
            ("job", segment_id): chunk
            for chunk in self.chunks
            for segment_id in chunk.segment_ids
            if ("job", segment_id) in wanted
        }

    def rebuild(self, **kwargs: object) -> None:
        raise AssertionError

    def clear(self) -> None:
        raise AssertionError

    def close(self) -> None:
        raise AssertionError


def test_lexical_response_uses_same_public_result_contract() -> None:
    lexical = Lexical((_match("s1", 3.0, 1),))
    response = TranscriptSearch(lexical=lexical).search(
        SearchQuery("housing"),
        mode=RetrievalMode.LEXICAL,
    )

    assert response.mode is RetrievalMode.LEXICAL
    assert response.lexical_backend_id == "lexical"
    assert response.results[0].segment_ids == ("s1",)
    assert response.results[0].matched_segment_ids == ("s1",)
    assert response.results[0].lexical_rank == 1
    assert response.results[0].semantic_rank is None
    assert response.results[0].canonical_sha256 == "1" * 64


def test_rrf_promotes_chunk_supported_by_both_independent_retrievers() -> None:
    a = _chunk("a", ("s1",), start=0, text="a")
    b = _chunk("b", ("s2",), start=1, text="b")
    c = _chunk("c", ("s3",), start=2, text="c")
    lexical = Lexical((_match("s1", 3.0, 0), _match("s2", 2.0, 1)))
    semantic = Semantic(
        (a, b, c),
        (
            SemanticCandidate(b, 0.9),
            SemanticCandidate(c, 0.8),
        ),
    )

    response = TranscriptSearch(
        lexical=lexical,
        semantic=semantic,
        embedding_provider=Provider(),
    ).search(SearchQuery("concept", limit=3), mode=RetrievalMode.HYBRID)

    assert [result.chunk_id for result in response.results] == ["b", "a", "c"]
    winner = response.results[0]
    assert winner.lexical_rank == 2
    assert winner.semantic_rank == 1
    assert winner.fused_rank == 1
    assert winner.matched_segment_ids == ("s2",)
    assert response.fusion_profile == "rrf-k60-v1"


def test_timeline_order_does_not_destroy_recorded_relevance_ranks() -> None:
    early = _chunk("a", ("s1",), start=0, text="early")
    late = _chunk("b", ("s2",), start=10, text="late")
    lexical = Lexical((_match("s2", 3.0, 10), _match("s1", 2.0, 0)))
    semantic = Semantic(
        (early, late),
        (
            SemanticCandidate(late, 0.9),
            SemanticCandidate(early, 0.8),
        ),
    )

    response = TranscriptSearch(
        lexical=lexical,
        semantic=semantic,
        embedding_provider=Provider(),
    ).search(
        SearchQuery("concept", sort=SearchSort.TIMELINE, limit=2),
        mode=RetrievalMode.HYBRID,
    )

    assert [result.chunk_id for result in response.results] == ["a", "b"]
    assert response.results[0].fused_rank == 2
    assert response.results[1].fused_rank == 1


def test_semantic_only_response_carries_embedding_provenance() -> None:
    chunk = _chunk("a", ("s1",), start=0, text="semantic")
    semantic = Semantic((chunk,), (SemanticCandidate(chunk, 0.7),))
    response = TranscriptSearch(
        lexical=Lexical(()),
        semantic=semantic,
        embedding_provider=Provider(),
    ).search(SearchQuery("concept"), mode=RetrievalMode.SEMANTIC)

    assert response.lexical_backend_id is None
    assert response.semantic_backend_id == "semantic"
    assert response.semantic_profile == _profile()
    assert response.results[0].semantic_rank == 1
