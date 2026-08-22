import hashlib
import json
from pathlib import Path

import pytest

from scholion.core.errors import ScholionError
from scholion.library.errors import PlaybackAuthorizationError
from scholion.library.index import IndexedDocument
from scholion.library.playback import PlaybackAuthorizationService, PlaybackGrant
from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind


class DocumentIndex:
    def __init__(self, documents: tuple[IndexedDocument, ...]) -> None:
        self._documents = documents

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self._documents


class MemoryFiles:
    def __init__(self, canonical: bytes, *, reported_size: int | None = None) -> None:
        self.canonical = canonical
        self.reported_size = reported_size

    def get_file_metadata(self, _path: str | Path) -> dict[str, int]:
        return {"size": self.reported_size or len(self.canonical)}

    def read_file(self, _path: str | Path) -> bytes:
        return self.canonical


class StaticProbe:
    def __init__(self, media: MediaInfo | BaseException) -> None:
        self.media = media

    def probe(self, _path: str | Path) -> MediaInfo:
        if isinstance(self.media, BaseException):
            raise self.media
        return self.media


class ProbeFailure(ScholionError):
    pass


def _canonical_payload(
    source_sha256: str,
    source_size: int,
    *,
    schema_version: int = 1,
    job_id: str = "job-1",
    canonical_source_sha256: str | None = None,
    duration_seconds: float = 8.5,
    audio_stream_index: int = 2,
) -> bytes:
    return json.dumps(
        {
            "schema_version": schema_version,
            "job_id": job_id,
            "source": {
                "sha256": canonical_source_sha256 or source_sha256,
                "size_bytes": source_size,
                "modified_ns": 42,
                "container_format": "mp4",
                "duration_seconds": duration_seconds,
                "audio_stream_index": audio_stream_index,
            },
        },
        sort_keys=True,
    ).encode()


def _document(
    canonical_path: Path,
    source_path: Path | None,
    source_sha256: str,
    canonical_sha256: str | None,
) -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256=source_sha256,
        detected_language="en",
        canonical_path=str(canonical_path),
        source_path=str(source_path) if source_path else None,
        segment_count=0,
        canonical_sha256=canonical_sha256,
    )


def _media(
    source: Path,
    source_sha256: str,
    source_size: int,
    *,
    audio_index: int = 2,
) -> MediaInfo:
    return MediaInfo(
        input=InputIdentity(
            path=source,
            size_bytes=source_size,
            modified_ns=42,
            sha256=source_sha256,
        ),
        container_format="mp4",
        duration_seconds=8.5,
        streams=(MediaStream(index=audio_index, kind=StreamKind.AUDIO, codec="aac"),),
        primary_audio_stream_index=audio_index,
    )


def _service(
    tmp_path: Path,
    *,
    payload: bytes | None = None,
    indexed_digest: str | None | object = ...,
    documents: bool = True,
    probe: MediaInfo | BaseException | None = None,
    reported_size: int | None = None,
) -> tuple[PlaybackAuthorizationService, str]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source evidence")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    canonical = tmp_path / "canonical.json"
    canonical_payload = payload or _canonical_payload(
        source_sha256,
        source.stat().st_size,
    )
    canonical.write_bytes(canonical_payload)
    digest = hashlib.sha256(canonical_payload).hexdigest()
    canonical_digest = digest if indexed_digest is ... else indexed_digest
    document = _document(
        canonical,
        source,
        source_sha256,
        canonical_digest if isinstance(canonical_digest, str) else None,
    )
    media = probe or _media(source, source_sha256, source.stat().st_size)
    service = PlaybackAuthorizationService(
        index=DocumentIndex((document,) if documents else ()),  # type: ignore[arg-type]
        file_manager=MemoryFiles(  # type: ignore[arg-type]
            canonical_payload,
            reported_size=reported_size,
        ),
        media_probe=StaticProbe(media),
    )
    return service, digest


def test_playback_grant_rejects_invalid_kind_and_seek() -> None:
    values = dict(
        document_id="job-1",
        canonical_sha256="a" * 64,
        source_sha256="b" * 64,
        source_path="source.mp4",
        source_size_bytes=10,
        source_modified_ns=42,
        duration_seconds=10.0,
        seek_seconds=2.0,
        audio_stream_index=0,
        media_kind="audio",
        container_format="mp4",
    )
    with pytest.raises(ValueError, match="media_kind"):
        PlaybackGrant(**{**values, "media_kind": "document"})
    with pytest.raises(ValueError, match="inside source duration"):
        PlaybackGrant(**{**values, "seek_seconds": 11.0})


def test_authorize_rejects_invalid_digest_blank_id_and_missing_document(
    tmp_path: Path,
) -> None:
    service, digest = _service(tmp_path)

    with pytest.raises(ValueError, match="lowercase 64-character"):
        service.authorize("job-1", expected_canonical_sha256="A" * 64, seek_seconds=1.0)
    with pytest.raises(ValueError, match="document_id cannot be blank"):
        service.authorize("   ", expected_canonical_sha256=digest, seek_seconds=1.0)

    missing, _ = _service(tmp_path, documents=False)
    with pytest.raises(
        PlaybackAuthorizationError, match="not present in the local library"
    ):
        missing.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_rejects_legacy_index_without_canonical_hash(tmp_path: Path) -> None:
    service, digest = _service(tmp_path, indexed_digest=None)

    with pytest.raises(PlaybackAuthorizationError, match="predates canonical hashing"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


@pytest.mark.parametrize(
    ("payload_mutation", "message"),
    [
        (lambda data: {**data, "schema_version": 2}, "unsupported schema version"),
        (lambda data: {**data, "job_id": "other-job"}, "identity no longer matches"),
        (
            lambda data: {
                **data,
                "source": {**data["source"], "sha256": "c" * 64},
            },
            "source identity no longer matches",
        ),
    ],
)
def test_authorize_rejects_canonical_identity_drift(
    tmp_path: Path,
    payload_mutation: object,
    message: str,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source evidence")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    base = json.loads(_canonical_payload(source_sha256, source.stat().st_size).decode())
    mutated = payload_mutation(base)  # type: ignore[operator]
    payload = json.dumps(mutated, sort_keys=True).encode()
    service, digest = _service(tmp_path, payload=payload)

    with pytest.raises(PlaybackAuthorizationError, match=message):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_normalizes_invalid_canonical_json(tmp_path: Path) -> None:
    payload = b"not-json"
    service, digest = _service(tmp_path, payload=payload)

    with pytest.raises(
        PlaybackAuthorizationError, match="could not be validated safely"
    ):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_rejects_canonical_size_guard_before_read(tmp_path: Path) -> None:
    service, digest = _service(tmp_path, reported_size=256 * 1024 * 1024 + 1)

    with pytest.raises(PlaybackAuthorizationError, match="too large"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_rejects_single_audio_stream_with_wrong_index(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source evidence")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    wrong_media = _media(source, source_sha256, source.stat().st_size, audio_index=3)
    service, digest = _service(tmp_path, probe=wrong_media)

    with pytest.raises(
        PlaybackAuthorizationError, match="audio stream no longer matches"
    ):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_normalizes_probe_failures_without_private_detail(
    tmp_path: Path,
) -> None:
    for failure in (
        ProbeFailure("private probe detail"),
        RuntimeError("private runtime detail"),
    ):
        service, digest = _service(tmp_path, probe=failure)
        with pytest.raises(
            PlaybackAuthorizationError,
            match="could not be verified safely for playback",
        ) as caught:
            service.authorize(
                "job-1", expected_canonical_sha256=digest, seek_seconds=1.0
            )
        assert "private" not in caught.value.public_message


def test_authorize_preserves_process_interrupts(tmp_path: Path) -> None:
    service, digest = _service(tmp_path, probe=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)

    service, digest = _service(tmp_path, probe=SystemExit())
    with pytest.raises(SystemExit):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)
