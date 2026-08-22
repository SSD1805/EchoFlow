"""Local evidence-first transcript library and rebuildable search contracts."""

from scholion.library.duckdb_index import DuckDbTranscriptIndex
from scholion.library.duckdb_semantic import DuckDbSemanticIndex
from scholion.library.evidence import (
    EvidenceContextSegment,
    EvidenceLocation,
    EvidenceLocator,
    EvidenceWord,
)
from scholion.library.index import (
    IndexedDocument,
    IndexedSegment,
    IndexedTranscript,
    SearchOperator,
    SearchQuery,
    SearchSort,
    TranscriptIndex,
    TranscriptMatch,
)
from scholion.library.research import (
    LocatedSearchPassage,
    ResearchNavigationService,
    ResearchSearchResponse,
    SpeakerDisplay,
)
from scholion.library.retrieval import (
    LexicalRetriever,
    RetrievalMode,
    SearchPassage,
    SearchResponse,
    TranscriptSearch,
)
from scholion.library.semantic import (
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
from scholion.library.service import (
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
    "EvidenceContextSegment",
    "EvidenceLocation",
    "EvidenceLocator",
    "EvidenceWord",
    "IndexedDocument",
    "IndexedSegment",
    "IndexedTranscript",
    "LexicalRetriever",
    "LibraryEvidenceReceipt",
    "LibraryRebuildReport",
    "LocatedSearchPassage",
    "ResearchNavigationService",
    "ResearchSearchResponse",
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
    "SpeakerDisplay",
    "TranscriptIndex",
    "TranscriptLibraryService",
    "TranscriptMatch",
    "TranscriptSearch",
    "build_search_chunks",
    "corpus_fingerprint",
]
