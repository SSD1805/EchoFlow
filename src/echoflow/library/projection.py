import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import TranscriptProjectionError
from echoflow.library.index import IndexedSegment, IndexedTranscript

_MAX_CANONICAL_BYTES = 256 * 1024 * 1024


class _SourceProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha256: str
    size_bytes: int
    modified_ns: int


class _SegmentProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    detected_language: str | None = None
    language: str | None = None
    speaker_ref: str | None = None


class _TranscriptProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int
    job_id: str
    source: _SourceProjection
    detected_language: str | None = None
    segments: list[_SegmentProjection]


def load_indexed_transcript(
    canonical_path: Path,
    *,
    source_path: Path | None,
    file_manager: FileManagerFacade,
) -> IndexedTranscript:
    """Validate the searchable projection of one authoritative canonical artifact."""
    try:
        payload = file_manager.read_file(canonical_path)
        if len(payload) > _MAX_CANONICAL_BYTES:
            raise TranscriptProjectionError(
                "Canonical transcript is too large to index safely"
            )
        document = _TranscriptProjection.model_validate(json.loads(payload))
        if document.schema_version != 1:
            raise TranscriptProjectionError(
                "Canonical transcript schema is unsupported by this EchoFlow build"
            )
        canonical = canonical_path.expanduser().resolve(strict=False)
        source = (
            None
            if source_path is None
            else source_path.expanduser().resolve(strict=False)
        )
        segments = tuple(
            IndexedSegment(
                segment_id=segment.segment_id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                language=(
                    segment.language
                    or segment.detected_language
                    or document.detected_language
                ),
                speaker_ref=segment.speaker_ref,
            )
            for segment in document.segments
        )
        return IndexedTranscript(
            document_id=document.job_id,
            source_sha256=document.source.sha256,
            canonical_sha256=hashlib.sha256(payload).hexdigest(),
            transcript_schema_version=document.schema_version,
            detected_language=document.detected_language,
            canonical_path=str(canonical),
            source_path=None if source is None else str(source),
            source_size_bytes=document.source.size_bytes,
            source_modified_ns=document.source.modified_ns,
            segments=segments,
        )
    except TranscriptProjectionError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise TranscriptProjectionError(
            "Canonical transcript could not be validated for local indexing",
            cause=exc,
        ) from exc
