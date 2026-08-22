from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, runtime_checkable

from scholion.library.index import (
    IndexedDocument,
    SearchQuery,
    SearchSort,
    TranscriptMatch,
)
from scholion.library.semantic import (
    EmbeddingProfile,
    EmbeddingProvider,
    EvidenceKey,
    SearchChunk,
    SemanticIndex,
)

_RRF_K = 60
_RRF_PROFILE = "rrf-k60-v1"
_CANDIDATE_MULTIPLIER = 5
_MIN_CANDIDATES = 100


class RetrievalMode(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@runtime_checkable
class LexicalRetriever(Protocol):
    @property
    def backend_id(self) -> str: ...

    def documents(self) -> tuple[IndexedDocument, ...]: ...

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]: ...


@dataclass(frozen=True, slots=True)
class SearchPassage:
    """Evidence-bearing result shaped for CLI, GUI, Python, and adapter surfaces."""

    document_id: str
    source_sha256: str
    canonical_sha256: str | None
    canonical_path: str
    source_path: str | None
    chunk_id: str | None
    segment_ids: tuple[str, ...]
    matched_segment_ids: tuple[str, ...]
    start_seconds: float
    end_seconds: float
    text: str
    languages: tuple[str, ...]
    speaker_refs: tuple[str, ...]
    lexical_rank: int | None
    semantic_rank: int | None
    fused_rank: int | None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.segment_ids:
            raise ValueError("search passage must reference at least one segment")
        if any(item not in self.segment_ids for item in self.matched_segment_ids):
            raise ValueError(
                "matched segments must belong to the result evidence window"
            )
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError(
                "search result timestamps must be ordered and non-negative"
            )
        if not self.text.strip():
            raise ValueError("search result text cannot be empty")
        for name in ("lexical_rank", "semantic_rank", "fused_rank"):
            rank = getattr(self, name)
            if rank is not None and rank < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Stable retrieval response with enough provenance to explain a result set."""

    query: SearchQuery
    mode: RetrievalMode
    lexical_backend_id: str | None
    semantic_backend_id: str | None
    semantic_profile: EmbeddingProfile | None
    fusion_profile: str | None
    results: tuple[SearchPassage, ...]

    def __post_init__(self) -> None:
        if self.mode is RetrievalMode.LEXICAL:
            if self.lexical_backend_id is None:
                raise ValueError("lexical response requires a lexical backend")
            if (
                self.semantic_backend_id is not None
                or self.semantic_profile is not None
            ):
                raise ValueError("lexical response cannot claim semantic provenance")
        else:
            if self.semantic_backend_id is None or self.semantic_profile is None:
                raise ValueError("semantic retrieval requires semantic provenance")
        if self.mode is RetrievalMode.HYBRID:
            if self.lexical_backend_id is None or self.fusion_profile is None:
                raise ValueError(
                    "hybrid response requires lexical and fusion provenance"
                )
        elif self.fusion_profile is not None:
            raise ValueError("non-hybrid response cannot claim fusion provenance")
        _validate_result_ranks(self.mode, self.results)


def _validate_result_ranks(
    mode: RetrievalMode, results: tuple[SearchPassage, ...]
) -> None:
    for result in results:
        if mode is RetrievalMode.LEXICAL and (
            result.semantic_rank is not None or result.fused_rank is not None
        ):
            raise ValueError("lexical results cannot claim semantic or fused rank")
        if mode is RetrievalMode.SEMANTIC and (
            result.lexical_rank is not None or result.fused_rank is not None
        ):
            raise ValueError("semantic results cannot claim lexical or fused rank")
        if mode is RetrievalMode.HYBRID and result.fused_rank is None:
            raise ValueError("hybrid results require fused rank")


class TranscriptSearch:
    """Compose narrow lexical and semantic retrievers without exposing storage details."""

    def __init__(
        self,
        *,
        lexical: LexicalRetriever,
        semantic: SemanticIndex | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.embedding_provider = embedding_provider

    def search(
        self, query: SearchQuery, *, mode: RetrievalMode = RetrievalMode.LEXICAL
    ) -> SearchResponse:
        if mode is RetrievalMode.LEXICAL:
            return self._lexical(query)
        semantic, provider = self._require_semantic()
        state = semantic.state()
        if state is None:
            raise ValueError("semantic index is empty; build embeddings first")
        if state.profile.identity_tuple() != provider.profile.identity_tuple():
            raise ValueError(
                "semantic model profile does not match the indexed vectors"
            )
        if mode is RetrievalMode.SEMANTIC:
            return self._semantic(query, semantic, provider)
        return self._hybrid(query, semantic, provider)

    def _lexical(self, query: SearchQuery) -> SearchResponse:
        documents = {item.document_id: item for item in self.lexical.documents()}
        matches = self.lexical.search(query)
        results = tuple(
            self._lexical_passage(
                match,
                documents.get(match.document_id),
                rank if query.sort is SearchSort.RELEVANCE else None,
            )
            for rank, match in enumerate(matches, start=1)
        )
        return SearchResponse(
            query=query,
            mode=RetrievalMode.LEXICAL,
            lexical_backend_id=self.lexical.backend_id,
            semantic_backend_id=None,
            semantic_profile=None,
            fusion_profile=None,
            results=results,
        )

    def _semantic(
        self,
        query: SearchQuery,
        semantic: SemanticIndex,
        provider: EmbeddingProvider,
    ) -> SearchResponse:
        query_vector = self._query_vector(provider, query.text)
        candidates = semantic.search(query, query_vector)
        results = tuple(
            self._chunk_passage(
                candidate.chunk,
                semantic_rank=rank,
                lexical_rank=None,
                fused_rank=None,
            )
            for rank, candidate in enumerate(candidates, start=1)
        )
        return SearchResponse(
            query=query,
            mode=RetrievalMode.SEMANTIC,
            lexical_backend_id=None,
            semantic_backend_id=semantic.backend_id,
            semantic_profile=provider.profile,
            fusion_profile=None,
            results=self._final_order(query, results)[: query.limit],
        )

    def _hybrid(
        self,
        query: SearchQuery,
        semantic: SemanticIndex,
        provider: EmbeddingProvider,
    ) -> SearchResponse:
        candidate_limit = min(
            1_000,
            max(query.limit * _CANDIDATE_MULTIPLIER, _MIN_CANDIDATES),
        )
        candidate_query = replace(
            query,
            limit=candidate_limit,
            sort=SearchSort.RELEVANCE,
        )
        lexical_matches = self.lexical.search(candidate_query)
        keys = tuple((match.document_id, match.segment_id) for match in lexical_matches)
        chunks_by_segment = semantic.chunks_for_segments(keys)
        lexical_ranks, matched_segments, chunks = self._collapse_lexical(
            lexical_matches, chunks_by_segment
        )

        query_vector = self._query_vector(provider, query.text)
        semantic_candidates = semantic.search(candidate_query, query_vector)
        semantic_ranks = {
            candidate.chunk.chunk_id: rank
            for rank, candidate in enumerate(semantic_candidates, start=1)
        }
        for candidate in semantic_candidates:
            chunks.setdefault(candidate.chunk.chunk_id, candidate.chunk)

        ranked_ids = sorted(
            chunks,
            key=lambda chunk_id: (
                -self._rrf_score(
                    lexical_ranks.get(chunk_id),
                    semantic_ranks.get(chunk_id),
                ),
                chunk_id,
            ),
        )
        relevance_rank = {
            chunk_id: rank for rank, chunk_id in enumerate(ranked_ids, start=1)
        }
        results = tuple(
            self._chunk_passage(
                chunks[chunk_id],
                lexical_rank=lexical_ranks.get(chunk_id),
                semantic_rank=semantic_ranks.get(chunk_id),
                fused_rank=relevance_rank[chunk_id],
                matched_segment_ids=tuple(
                    sorted(
                        matched_segments.get(chunk_id, set()),
                        key=chunks[chunk_id].segment_ids.index,
                    )
                ),
            )
            for chunk_id in ranked_ids[: query.limit]
        )
        return SearchResponse(
            query=query,
            mode=RetrievalMode.HYBRID,
            lexical_backend_id=self.lexical.backend_id,
            semantic_backend_id=semantic.backend_id,
            semantic_profile=provider.profile,
            fusion_profile=_RRF_PROFILE,
            results=self._final_order(query, results),
        )

    @staticmethod
    def _collapse_lexical(
        matches: tuple[TranscriptMatch, ...],
        chunks_by_segment: dict[EvidenceKey, SearchChunk],
    ) -> tuple[dict[str, int], dict[str, set[str]], dict[str, SearchChunk]]:
        ranks: dict[str, int] = {}
        matched: dict[str, set[str]] = {}
        chunks: dict[str, SearchChunk] = {}
        for raw_rank, match in enumerate(matches, start=1):
            key = (match.document_id, match.segment_id)
            chunk = chunks_by_segment.get(key)
            if chunk is None:
                continue
            chunks[chunk.chunk_id] = chunk
            ranks.setdefault(chunk.chunk_id, raw_rank)
            matched.setdefault(chunk.chunk_id, set()).add(match.segment_id)
        ordered = sorted(ranks, key=lambda chunk_id: (ranks[chunk_id], chunk_id))
        collapsed_ranks = {
            chunk_id: rank for rank, chunk_id in enumerate(ordered, start=1)
        }
        return collapsed_ranks, matched, chunks

    @staticmethod
    def _rrf_score(lexical_rank: int | None, semantic_rank: int | None) -> float:
        score = 0.0
        if lexical_rank is not None:
            score += 1.0 / (_RRF_K + lexical_rank)
        if semantic_rank is not None:
            score += 1.0 / (_RRF_K + semantic_rank)
        return score

    @staticmethod
    def _query_vector(provider: EmbeddingProvider, text: str) -> tuple[float, ...]:
        vectors = provider.embed_queries((text,))
        if len(vectors) != 1:
            raise RuntimeError(
                "embedding provider returned an invalid query vector count"
            )
        return vectors[0]

    @staticmethod
    def _lexical_passage(
        match: TranscriptMatch,
        document: IndexedDocument | None,
        rank: int | None,
    ) -> SearchPassage:
        return SearchPassage(
            document_id=match.document_id,
            source_sha256=match.source_sha256,
            canonical_sha256=(None if document is None else document.canonical_sha256),
            canonical_path=match.canonical_path,
            source_path=match.source_path,
            chunk_id=None,
            segment_ids=(match.segment_id,),
            matched_segment_ids=(match.segment_id,),
            start_seconds=match.start_seconds,
            end_seconds=match.end_seconds,
            text=match.text,
            languages=() if match.language is None else (match.language,),
            speaker_refs=() if match.speaker_ref is None else (match.speaker_ref,),
            lexical_rank=rank,
            semantic_rank=None,
            fused_rank=None,
        )

    @staticmethod
    def _chunk_passage(
        chunk: SearchChunk,
        *,
        lexical_rank: int | None,
        semantic_rank: int | None,
        fused_rank: int | None,
        matched_segment_ids: tuple[str, ...] = (),
    ) -> SearchPassage:
        return SearchPassage(
            document_id=chunk.document_id,
            source_sha256=chunk.source_sha256,
            canonical_sha256=chunk.canonical_sha256,
            canonical_path=chunk.canonical_path,
            source_path=chunk.source_path,
            chunk_id=chunk.chunk_id,
            segment_ids=chunk.segment_ids,
            matched_segment_ids=matched_segment_ids,
            start_seconds=chunk.start_seconds,
            end_seconds=chunk.end_seconds,
            text=chunk.text,
            languages=chunk.languages,
            speaker_refs=chunk.speaker_refs,
            lexical_rank=lexical_rank,
            semantic_rank=semantic_rank,
            fused_rank=fused_rank,
        )

    @staticmethod
    def _final_order(
        query: SearchQuery, results: tuple[SearchPassage, ...]
    ) -> tuple[SearchPassage, ...]:
        if query.sort is SearchSort.RELEVANCE:
            return results
        return tuple(
            sorted(
                results,
                key=lambda result: (
                    result.document_id,
                    result.start_seconds,
                    result.segment_ids[0],
                ),
            )
        )

    def _require_semantic(self) -> tuple[SemanticIndex, EmbeddingProvider]:
        if self.semantic is None or self.embedding_provider is None:
            raise ValueError("semantic retrieval is not configured")
        return self.semantic, self.embedding_provider
