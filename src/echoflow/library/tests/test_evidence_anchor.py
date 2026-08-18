import hashlib
import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import EvidenceNavigationError
from echoflow.library.evidence import EvidenceLocator
from echoflow.library.index import IndexedDocument


def _canonical(path: Path) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "job_id": "job-1",
            "source": {"sha256": "a" * 64},
            "segments": [
                {
                    "segment_id": "segment-000001",
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "text": "First evidence.",
                },
                {
                    "segment_id": "segment-000002",
                    "start_seconds": 2.0,
                    "end_seconds": 3.0,
                    "text": "Second evidence.",
                },
                {
                    "segment_id": "segment-000003",
                    "start_seconds": 3.0,
                    "end_seconds": 4.0,
                    "text": "Third evidence.",
                },
            ],
        },
        sort_keys=True,
    ).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _document(path: Path, digest: str) -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=digest,
        detected_language="en",
        canonical_path=str(path),
        source_path="/recording.wav",
        segment_count=3,
    )


def _locator() -> EvidenceLocator:
    return EvidenceLocator(LocalFileManager())  # type: ignore[arg-type]


def test_anchor_resolves_contiguous_canonical_evidence(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    digest = _canonical(path)

    anchor = _locator().resolve_anchor(
        _document(path, digest),
        ("segment-000001", "segment-000002"),
        start_seconds=1.25,
        end_seconds=2.75,
    )

    assert anchor.document_id == "job-1"
    assert anchor.canonical_sha256 == digest
    assert anchor.segment_ids == ("segment-000001", "segment-000002")
    assert anchor.start_seconds == 1.25
    assert anchor.end_seconds == 2.75


def test_anchor_rejects_noncontiguous_or_reordered_segments(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    digest = _canonical(path)
    document = _document(path, digest)

    with pytest.raises(EvidenceNavigationError, match="contiguous"):
        _locator().resolve_anchor(
            document,
            ("segment-000001", "segment-000003"),
        )
    with pytest.raises(EvidenceNavigationError, match="contiguous"):
        _locator().resolve_anchor(
            document,
            ("segment-000002", "segment-000001"),
        )


def test_anchor_refuses_stale_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    digest = _canonical(path)
    document = _document(path, digest)
    path.write_text('{"schema_version": 1}')

    with pytest.raises(EvidenceNavigationError, match="changed"):
        _locator().resolve_anchor(document, ("segment-000001",))


def test_anchor_subrange_cannot_escape_selected_evidence(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    digest = _canonical(path)
    document = _document(path, digest)

    with pytest.raises(EvidenceNavigationError, match="inside"):
        _locator().resolve_anchor(
            document,
            ("segment-000002",),
            start_seconds=1.5,
            end_seconds=2.5,
        )
