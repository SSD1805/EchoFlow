"""Local evidence-first transcript library and rebuildable search contracts."""

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.duckdb_semantic import DuckDbSemanticIndex
from echoflow.library.index import (
    IndexedDocument,
    IndexedSegment,
    IndexedTranscript,
    SearchOperator,
    SearchQuery,
    SearchSort,
    TranscriptIndex,
    TranscriptMatch,
)
from echoflow.library.retrieval import (
    LexicalRetriever,
    RetrievalMode,
    SearchPassage,
    SearchResponse,
    TranscriptSearch,
)
from echoflow.library.semantic import (
    ChunkingProfile,
    EmbeddingProfile,
    EmbeddingProvider,
    EmbeddingVector,
    SearchChunk,
    SemanticCandidate,
    SemanticIndex,
    SemanticState,
    SentenceTransformersE5Provider,
    build_search_chunks,
    corpus_fingerprint,
)
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    LibraryRebuildReport,
    SemanticRebuildReport,
    SourceIntegrity,
    TranscriptLibraryService,
)

__all__ = [
    "ChunkingProfile",
    "DuckDbSemanticIndex",
    "DuckDbTranscriptIndex",
    "EmbeddingProfile",
    "EmbeddingProvider",
    "EmbeddingVector",
    "IndexedDocument",
    "IndexedSegment",
    "IndexedTranscript",
    "LexicalRetriever",
    "LibraryEvidenceReceipt",
    "LibraryRebuildReport",
    "RetrievalMode",
    "SearchChunk",
    "SearchOperator",
    "SearchPassage",
    "SearchQuery",
    "SearchResponse",
    "SearchSort",
    "SemanticCandidate",
    "SemanticIndex",
    "SemanticRebuildReport",
    "SemanticState",
    "SentenceTransformersE5Provider",
    "SourceIntegrity",
    "TranscriptIndex",
    "TranscriptLibraryService",
    "TranscriptMatch",
    "TranscriptSearch",
    "build_search_chunks",
    "corpus_fingerprint",
]
