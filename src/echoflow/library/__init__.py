"""Derived transcript-library indexing contracts.

Canonical transcript artifacts remain authoritative. Index backends are rebuildable
acceleration/search layers and must never become checkpoint or transcript custody.
"""

from echoflow.library.index import (
    IndexedSegment,
    IndexedTranscript,
    TranscriptIndex,
    TranscriptMatch,
    TranscriptQuery,
)

__all__ = [
    "IndexedSegment",
    "IndexedTranscript",
    "TranscriptIndex",
    "TranscriptMatch",
    "TranscriptQuery",
]
