"""Local evidence-first transcript library and rebuildable search contracts."""

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
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
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    LibraryRebuildReport,
    SourceIntegrity,
    TranscriptLibraryService,
)

__all__ = [
    "DuckDbTranscriptIndex",
    "IndexedDocument",
    "IndexedSegment",
    "IndexedTranscript",
    "LibraryEvidenceReceipt",
    "LibraryRebuildReport",
    "SearchOperator",
    "SearchQuery",
    "SearchSort",
    "SourceIntegrity",
    "TranscriptIndex",
    "TranscriptLibraryService",
    "TranscriptMatch",
]
