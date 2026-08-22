"""Pure desktop presentation serializers for Research evidence.

These helpers translate already-authorized application objects into the stable frontend
shape. They do not resolve evidence, choose generations, query storage, or expose paths.
Keeping the presentation contract here prevents basic discovery and typed Research search
from drifting into subtly different meanings of the same evidence result.
"""

from __future__ import annotations

from scholion.library.evidence import EvidenceContextSegment, EvidenceWord
from scholion.library.research_workspace import WorkspaceSearchPassage


def serialize_word(word: EvidenceWord) -> dict[str, object]:
    """Serialize one evidence word without adding authority or filesystem state."""
    return {
        "segment_id": word.segment_id,
        "word_index": word.word_index,
        "start_seconds": word.start_seconds,
        "end_seconds": word.end_seconds,
        "text": word.text,
        "speaker_ref": word.speaker_ref,
        "highlighted": word.highlighted,
    }


def serialize_context_segment(segment: EvidenceContextSegment) -> dict[str, object]:
    """Serialize one contextual transcript segment and its evidence words."""
    return {
        "segment_id": segment.segment_id,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
        "speaker_refs": list(segment.speaker_refs),
        "words": [serialize_word(word) for word in segment.words],
        "is_result_segment": segment.is_result_segment,
        "lexical_match": segment.lexical_match,
    }


def serialize_workspace_passage(item: WorkspaceSearchPassage) -> dict[str, object]:
    """Serialize the canonical desktop contract for a verified Research passage."""
    return {
        "document_id": item.located.evidence.document_id,
        "source_sha256": item.located.evidence.source_sha256,
        "canonical_sha256": item.located.evidence.canonical_sha256,
        "segment_ids": list(item.located.evidence.result_segment_ids),
        "text": item.located.passage.text,
        "start_seconds": item.located.evidence.start_seconds,
        "end_seconds": item.located.evidence.end_seconds,
        "seek_seconds": item.located.evidence.seek_seconds,
        "languages": list(item.located.passage.languages),
        "speakers": [
            {
                "speaker_ref": speaker.speaker_ref,
                "display_label": speaker.display_label,
            }
            for speaker in item.located.speakers
        ],
        "matched_words": [
            serialize_word(word) for word in item.located.evidence.matched_words
        ],
        "context_segments": [
            serialize_context_segment(segment)
            for segment in item.located.evidence.context_segments
        ],
        "note_count": item.research.note_count,
        "tags": list(item.research.tags),
        "collections": list(item.research.collections),
    }
