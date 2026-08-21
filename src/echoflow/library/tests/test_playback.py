import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import PlaybackAuthorizationError
from echoflow.library.index import IndexedDocument
from echoflow.library.playback import PlaybackAuthorizationService
from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind


class DocumentIndex:
    def __init__(self, documents: tuple[IndexedDocument, ...]) -> None:
        self._documents = documents

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self._documents


class StaticMediaProbe:
    def __init__(self, media: MediaInfo | Exception) -> None:
        self.media = media
        self.paths: list[Path] = []

    def probe(self, input_path: str | Path) -> MediaInfo:
        self.paths.append(Path(input_path))
        if isinstance(self.media, Exception):
            raise self.media
        return self.media


def _canonical(path: Path, *, source_sha256: str, source_size: int) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "job_id": "job-1",
            "source": {
                "sha256": source_sha256,
                "size_bytes": source_size,
                "modified_ns": 42,
                "container_format": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration_seconds": 8.5,
                "audio_stream_index": 2,
            },
            "segments": [],
        },
        sort_keys=True,
    ).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _media(
    source: Path,
    *,
    source_sha256: str,
    source_size: int,
    audio_indices: tuple[int, ...] = (2,),
    video: bool = False,
) -> MediaInfo:
    streams = [
        MediaStream(index=index, kind=StreamKind.AUDIO, codec="aac")
        for index in audio_indices
    ]
    if video:
        streams.append(MediaStream(index=0, kind=StreamKind.VIDEO, codec="h264"))
    return MediaInfo(
        input=InputIdentity(
            path=source,
            size_bytes=source_size,
            modified_ns=42,
            sha256=source_sha256,
        ),
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_seconds=8.5,
        streams=tuple(streams),
        primary_audio_stream_index=audio_indices[0],
    )


def _service(
    tmp_path: Path,
    *,
    source_exists: bool = True,
    probe_sha256: str | None = None,
    probe_size: int | None = None,
    audio_indices: tuple[int, ...] = (2,),
    video: bool = False,
    source_path_known: bool = True,
) -> tuple[PlaybackAuthorizationService, StaticMediaProbe, str, Path, str]:
    source = tmp_path / "interview.mp4"
    source_bytes = b"verified local recording bytes"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if source_exists:
        source.write_bytes(source_bytes)
    source_size = len(source_bytes)
    canonical = tmp_path / "interview.json"
    canonical_sha256 = _canonical(
        canonical,
        source_sha256=source_sha256,
        source_size=source_size,
    )
    document = IndexedDocument(
        document_id="job-1",
        source_sha256=source_sha256,
        detected_language="en",
        canonical_path=str(canonical.resolve()),
        source_path=str(source.resolve()) if source_path_known else None,
        segment_count=0,
        canonical_sha256=canonical_sha256,
    )
    probe = StaticMediaProbe(
        _media(
            source,
            source_sha256=probe_sha256 or source_sha256,
            source_size=source_size if probe_size is None else probe_size,
            audio_indices=audio_indices,
            video=video,
        )
    )
    return (
        PlaybackAuthorizationService(
            index=DocumentIndex((document,)),  # type: ignore[arg-type]
            file_manager=LocalFileManager(),  # type: ignore[arg-type]
            media_probe=probe,
        ),
        probe,
        canonical_sha256,
        source,
        source_sha256,
    )


def test_authorize_binds_exact_generation_source_and_seek(tmp_path: Path) -> None:
    service, probe, canonical_sha256, source, source_sha256 = _service(tmp_path)

    grant = service.authorize(
        "job-1",
        expected_canonical_sha256=canonical_sha256,
        seek_seconds=3.25,
    )

    assert grant.document_id == "job-1"
    assert grant.canonical_sha256 == canonical_sha256
    assert grant.source_sha256 == source_sha256
    assert grant.source_path == str(source.resolve())
    assert grant.seek_seconds == 3.25
    assert grant.duration_seconds == 8.5
    assert grant.audio_stream_index == 2
    assert grant.media_kind == "audio"
    assert probe.paths == [source.resolve()]


def test_authorize_detects_video_without_changing_audio_evidence(tmp_path: Path) -> None:
    service, _, canonical_sha256, _, _ = _service(tmp_path, video=True)

    grant = service.authorize(
        "job-1",
        expected_canonical_sha256=canonical_sha256,
        seek_seconds=0.0,
    )

    assert grant.media_kind == "video"
    assert grant.audio_stream_index == 2


def test_authorize_rejects_stale_generation_before_source_probe(tmp_path: Path) -> None:
    service, probe, _, _, _ = _service(tmp_path)

    with pytest.raises(PlaybackAuthorizationError, match="changed since this evidence view"):
        service.authorize(
            "job-1",
            expected_canonical_sha256="b" * 64,
            seek_seconds=1.0,
        )

    assert probe.paths == []


def test_authorize_rejects_missing_or_unknown_source_path(tmp_path: Path) -> None:
    missing, probe, digest, _, _ = _service(tmp_path, source_exists=False)
    with pytest.raises(PlaybackAuthorizationError, match="unavailable at its recorded location"):
        missing.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)
    assert probe.paths == []

    unknown, _, digest, _, _ = _service(
        tmp_path / "unknown",
        source_path_known=False,
    ) if False else (None, None, None, None, None)


def test_authorize_rejects_unknown_source_location(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    service, probe, digest, _, _ = _service(tmp_path, source_path_known=False)

    with pytest.raises(PlaybackAuthorizationError, match="location is unavailable"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)

    assert probe.paths == []


def test_authorize_rejects_source_hash_or_size_mismatch(tmp_path: Path) -> None:
    service, _, digest, _, _ = _service(tmp_path, probe_sha256="b" * 64)
    with pytest.raises(PlaybackAuthorizationError, match="no longer matches the source"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)

    service, _, digest, _, _ = _service(tmp_path, probe_size=999)
    with pytest.raises(PlaybackAuthorizationError, match="size no longer matches"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_rejects_multi_audio_instead_of_guessing_track(tmp_path: Path) -> None:
    service, _, digest, _, _ = _service(tmp_path, audio_indices=(2, 4))

    with pytest.raises(PlaybackAuthorizationError, match="multiple audio streams"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)


def test_authorize_rejects_tampered_canonical_and_out_of_range_seek(tmp_path: Path) -> None:
    service, probe, digest, _, _ = _service(tmp_path)
    (tmp_path / "interview.json").write_text("{}")

    with pytest.raises(PlaybackAuthorizationError, match="Canonical transcript changed"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=1.0)
    assert probe.paths == []

    service, _, digest, _, _ = _service(tmp_path)
    with pytest.raises(PlaybackAuthorizationError, match="outside the verified recording"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=8.5001)


@pytest.mark.parametrize("seek", [-1.0, math.inf, -math.inf, math.nan])
def test_authorize_rejects_invalid_seek_shapes(tmp_path: Path, seek: float) -> None:
    service, probe, digest, _, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="finite and non-negative"):
        service.authorize("job-1", expected_canonical_sha256=digest, seek_seconds=seek)

    assert probe.paths == []


@given(st.floats(min_value=0.0, max_value=8.5, allow_nan=False, allow_infinity=False))
def test_all_finite_seeks_inside_verified_duration_are_preserved(seek: float) -> None:
    with TemporaryDirectory() as directory:
        service, _, digest, _, _ = _service(Path(directory))

        grant = service.authorize(
            "job-1",
            expected_canonical_sha256=digest,
            seek_seconds=seek,
        )

        assert grant.seek_seconds == seek
