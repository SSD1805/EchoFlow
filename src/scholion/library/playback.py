"""Generation-bound authorization for native playback of verified local source evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scholion.core.errors import ScholionError
from scholion.core.file_manager_facade import FileManagerFacade
from scholion.library.errors import PlaybackAuthorizationError
from scholion.library.index import IndexedDocument, TranscriptIndex
from scholion.media.models import MediaInfo, StreamKind

_MAX_CANONICAL_BYTES = 256 * 1024 * 1024


class _CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    modified_ns: int = Field(ge=0)
    container_format: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    audio_stream_index: int = Field(ge=0)


class _CanonicalPlaybackProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int
    job_id: str = Field(min_length=1)
    source: _CanonicalSource


class MediaProbe(Protocol):
    """Read-only media inspection needed by playback authorization."""

    def probe(self, input_path: str | Path) -> MediaInfo: ...


@dataclass(frozen=True, slots=True)
class PlaybackGrant:
    """Trusted-host grant. ``source_path`` must never cross into the webview DTO."""

    document_id: str
    canonical_sha256: str
    source_sha256: str
    source_path: str
    source_size_bytes: int
    source_modified_ns: int
    duration_seconds: float
    seek_seconds: float
    audio_stream_index: int
    media_kind: str
    container_format: str

    def __post_init__(self) -> None:
        if self.media_kind not in {"audio", "video"}:
            raise ValueError("media_kind must be audio or video")
        if not math.isfinite(self.seek_seconds) or not (
            0 <= self.seek_seconds <= self.duration_seconds
        ):
            raise ValueError("seek_seconds must remain inside source duration")


class PlaybackAuthorizationService:
    """Authorize playback only when canonical generation and source bytes still agree."""

    def __init__(
        self,
        *,
        index: TranscriptIndex,
        file_manager: FileManagerFacade,
        media_probe: MediaProbe,
    ) -> None:
        self.index = index
        self.file_manager = file_manager
        self.media_probe = media_probe

    def authorize(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        seek_seconds: float,
    ) -> PlaybackGrant:
        self._validate_seek_shape(seek_seconds)
        document = self._require_generation(document_id, expected_canonical_sha256)
        projection = self._verified_projection(document, expected_canonical_sha256)
        source_path = self._require_source_path(document)
        media = self._verified_source(source_path, projection, document)

        if seek_seconds > projection.source.duration_seconds:
            raise PlaybackAuthorizationError(
                "Playback position is outside the verified recording duration"
            )

        audio_streams = tuple(
            stream for stream in media.streams if stream.kind is StreamKind.AUDIO
        )
        if len(audio_streams) != 1:
            raise PlaybackAuthorizationError(
                "Playback for recordings with multiple audio streams is not enabled yet; "
                "Scholion will not guess which track matches this transcript"
            )
        if audio_streams[0].index != projection.source.audio_stream_index:
            raise PlaybackAuthorizationError(
                "The verified source audio stream no longer matches this transcript"
            )

        return PlaybackGrant(
            document_id=document.document_id,
            canonical_sha256=expected_canonical_sha256,
            source_sha256=projection.source.sha256,
            source_path=str(media.input.path),
            source_size_bytes=media.input.size_bytes,
            source_modified_ns=media.input.modified_ns,
            duration_seconds=projection.source.duration_seconds,
            seek_seconds=seek_seconds,
            audio_stream_index=projection.source.audio_stream_index,
            media_kind=(
                "video"
                if any(stream.kind is StreamKind.VIDEO for stream in media.streams)
                else "audio"
            ),
            container_format=projection.source.container_format,
        )

    @staticmethod
    def _validate_seek_shape(seek_seconds: float) -> None:
        if not math.isfinite(seek_seconds) or seek_seconds < 0:
            raise ValueError("seek_seconds must be finite and non-negative")

    def _require_generation(
        self, document_id: str, expected_canonical_sha256: str
    ) -> IndexedDocument:
        if len(expected_canonical_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in expected_canonical_sha256
        ):
            raise ValueError(
                "expected_canonical_sha256 must be a lowercase 64-character digest"
            )
        normalized_id = document_id.strip()
        if not normalized_id:
            raise ValueError("document_id cannot be blank")
        document = next(
            (
                item
                for item in self.index.documents()
                if item.document_id == normalized_id
            ),
            None,
        )
        if document is None:
            raise PlaybackAuthorizationError(
                "Transcript is not present in the local library"
            )
        if document.canonical_sha256 is None:
            raise PlaybackAuthorizationError(
                "Transcript index predates canonical hashing; rebuild the library first"
            )
        if document.canonical_sha256 != expected_canonical_sha256:
            raise PlaybackAuthorizationError(
                "Transcript changed since this evidence view was opened; reopen it before playback"
            )
        return document

    def _verified_projection(
        self, document: IndexedDocument, expected_canonical_sha256: str
    ) -> _CanonicalPlaybackProjection:
        try:
            path = Path(document.canonical_path)
            metadata = self.file_manager.get_file_metadata(path)
            if metadata["size"] > _MAX_CANONICAL_BYTES:
                raise PlaybackAuthorizationError(
                    "Canonical transcript is too large to authorize playback safely"
                )
            payload = self.file_manager.read_file(path)
            if hashlib.sha256(payload).hexdigest() != expected_canonical_sha256:
                raise PlaybackAuthorizationError(
                    "Canonical transcript changed; rebuild the library before playback"
                )
            projection = _CanonicalPlaybackProjection.model_validate(
                json.loads(payload)
            )
            if projection.schema_version != 1:
                raise PlaybackAuthorizationError(
                    "Canonical transcript uses an unsupported schema version"
                )
            if projection.job_id != document.document_id:
                raise PlaybackAuthorizationError(
                    "Canonical transcript identity no longer matches the library index"
                )
            if projection.source.sha256 != document.source_sha256:
                raise PlaybackAuthorizationError(
                    "Canonical transcript source identity no longer matches the library index"
                )
            if not math.isfinite(projection.source.duration_seconds):
                raise PlaybackAuthorizationError(
                    "Canonical recording duration is not valid for playback"
                )
            return projection
        except PlaybackAuthorizationError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise PlaybackAuthorizationError(
                "Canonical transcript could not be validated safely for playback",
                cause=exc,
            ) from exc

    @staticmethod
    def _require_source_path(document: IndexedDocument) -> Path:
        if document.source_path is None:
            raise PlaybackAuthorizationError(
                "Original recording location is unavailable; reconnect the source before playback"
            )
        source = Path(document.source_path).expanduser().resolve(strict=False)
        if not source.is_file():
            raise PlaybackAuthorizationError(
                "Original recording is unavailable at its recorded location"
            )
        return source

    def _verified_source(
        self,
        source_path: Path,
        projection: _CanonicalPlaybackProjection,
        document: IndexedDocument,
    ) -> MediaInfo:
        try:
            media = self.media_probe.probe(source_path)
        except (KeyboardInterrupt, SystemExit):
            raise
        except ScholionError as exc:
            raise PlaybackAuthorizationError(
                "Original recording could not be verified safely for playback",
                cause=exc,
            ) from exc
        except Exception as exc:
            raise PlaybackAuthorizationError(
                "Original recording could not be verified safely for playback",
                cause=exc,
            ) from exc

        expected_sha = projection.source.sha256
        if (
            media.input.sha256 != expected_sha
            or media.input.sha256 != document.source_sha256
        ):
            raise PlaybackAuthorizationError(
                "Original recording no longer matches the source used for this transcript"
            )
        if media.input.size_bytes != projection.source.size_bytes:
            raise PlaybackAuthorizationError(
                "Original recording size no longer matches canonical source provenance"
            )
        return media
