import json
from pathlib import Path

import pytest

from echoflow.library import projection
from echoflow.library.errors import TranscriptProjectionError
from echoflow.library.projection import load_indexed_transcript


class ReadStore:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read_file(self, file_path: str | Path) -> bytes:
        return self.payload


class MutatingReadStore:
    def read_file(self, file_path: str | Path) -> bytes:
        path = Path(file_path)
        payload = path.read_bytes()
        path.write_bytes(payload + b" ")
        return payload


def _document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": "job-1",
        "source": {"sha256": "0" * 64, "size_bytes": 42, "modified_ns": 7},
        "detected_language": "en",
        "segments": [
            {
                "segment_id": "segment-000000",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "text": "hello",
                "language": "fr",
                "detected_language": "en",
                "speaker_ref": "speaker-01",
                "words": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "text": " hello",
                        "probability": 0.91,
                        "speaker_ref": "speaker-01",
                    }
                ],
            },
            {
                "segment_id": "segment-000001",
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "text": "world",
                "detected_language": "de",
            },
            {
                "segment_id": "segment-000002",
                "start_seconds": 2.0,
                "end_seconds": 3.0,
                "text": "again",
            },
        ],
        "ignored_future_field": {"safe": True},
    }


def _canonical(tmp_path: Path, payload: bytes) -> Path:
    path = tmp_path / "transcript.json"
    path.write_bytes(payload)
    return path


def test_projection_extracts_only_searchable_canonical_evidence(tmp_path: Path) -> None:
    payload = json.dumps(_document()).encode()
    canonical = _canonical(tmp_path, payload)
    source = tmp_path / "audio.wav"

    indexed = load_indexed_transcript(
        canonical,
        source_path=source,
        file_manager=ReadStore(payload),  # type: ignore[arg-type]
    )

    assert indexed.document_id == "job-1"
    assert indexed.source_sha256 == "0" * 64
    assert indexed.canonical_path == str(canonical.resolve())
    assert indexed.source_path == str(source.resolve())
    assert indexed.canonical_size_bytes == len(payload)
    assert indexed.canonical_modified_ns == canonical.stat().st_mtime_ns
    assert [segment.language for segment in indexed.segments] == ["fr", "de", "en"]
    assert indexed.segments[0].speaker_ref == "speaker-01"
    assert indexed.segments[0].text == "hello"


def test_projection_accepts_unknown_source_path(tmp_path: Path) -> None:
    payload = json.dumps(_document()).encode()
    canonical = _canonical(tmp_path, payload)
    indexed = load_indexed_transcript(
        canonical,
        source_path=None,
        file_manager=ReadStore(payload),  # type: ignore[arg-type]
    )
    assert indexed.source_path is None


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"not-json", "could not be validated"),
        (json.dumps({"schema_version": 1}).encode(), "could not be validated"),
        (
            json.dumps({**_document(), "schema_version": 99}).encode(),
            "schema is unsupported",
        ),
        (
            json.dumps(
                {
                    **_document(),
                    "segments": [
                        {
                            "segment_id": "segment-000000",
                            "start_seconds": 2,
                            "end_seconds": 1,
                            "text": "bad",
                        }
                    ],
                }
            ).encode(),
            "could not be validated",
        ),
    ],
)
def test_projection_fails_closed_on_malformed_canonical_data(
    tmp_path: Path, payload: bytes, message: str
) -> None:
    canonical = _canonical(tmp_path, payload)
    with pytest.raises(TranscriptProjectionError, match=message):
        load_indexed_transcript(
            canonical,
            source_path=None,
            file_manager=ReadStore(payload),  # type: ignore[arg-type]
        )


def test_projection_rejects_oversized_artifact_before_json_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(projection, "_MAX_CANONICAL_BYTES", 4)
    payload = b"12345"
    canonical = _canonical(tmp_path, payload)
    with pytest.raises(TranscriptProjectionError, match="too large"):
        load_indexed_transcript(
            canonical,
            source_path=None,
            file_manager=ReadStore(payload),  # type: ignore[arg-type]
        )


def test_projection_fails_closed_if_canonical_changes_during_read(tmp_path: Path) -> None:
    payload = json.dumps(_document()).encode()
    canonical = _canonical(tmp_path, payload)

    with pytest.raises(TranscriptProjectionError, match="changed while"):
        load_indexed_transcript(
            canonical,
            source_path=None,
            file_manager=MutatingReadStore(),  # type: ignore[arg-type]
        )
