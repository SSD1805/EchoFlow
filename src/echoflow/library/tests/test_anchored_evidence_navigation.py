import hashlib
import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import EvidenceNavigationError
from echoflow.library.evidence import EvidenceAnchor, EvidenceLocator


def _write_canonical(path: Path) -> str:
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
                    "text": "Before the cited passage.",
                    "speaker_ref": "speaker-01",
                    "words": [],
                },
                {
                    "segment_id": "segment-000002",
                    "start_seconds": 2.0,
                    "end_seconds": 3.0,
                    "text": "The exact cited passage.",
                    "speaker_ref": "speaker-02",
                    "words": [
                        {
                            "start_seconds": 2.0,
                            "end_seconds": 2.2,
                            "text": "The",
                            "speaker_ref": "speaker-02",
                        }
                    ],
                },
                {
                    "segment_id": "segment-000003",
                    "start_seconds": 3.0,
                    "end_seconds": 4.0,
                    "text": "After the cited passage.",
                    "speaker_ref": "speaker-01",
                    "words": [],
                },
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _anchor(path: Path, digest: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=digest,
        canonical_path=str(path),
        source_path="/recording.wav",
        segment_ids=("segment-000002",),
        start_seconds=2.1,
        end_seconds=2.9,
    )


def _locator() -> EvidenceLocator:
    return EvidenceLocator(LocalFileManager())  # type: ignore[arg-type]


def test_anchor_reopens_exact_generation_with_context_and_no_query_highlights(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old-generation.json"
    digest = _write_canonical(path)

    located = _locator().locate_anchor(_anchor(path, digest), context_segments=1)

    assert located.canonical_sha256 == digest
    assert located.result_segment_ids == ("segment-000002",)
    assert located.start_seconds == 2.1
    assert located.end_seconds == 2.9
    assert located.seek_seconds == 2.1
    assert located.result_speaker_refs == ("speaker-02",)
    assert [segment.segment_id for segment in located.context_segments] == [
        "segment-000001",
        "segment-000002",
        "segment-000003",
    ]
    assert located.context_segments[1].is_result_segment
    assert not located.context_segments[1].lexical_match
    assert located.matched_words == ()


def test_anchor_reopen_refuses_changed_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "old-generation.json"
    digest = _write_canonical(path)
    anchor = _anchor(path, digest)
    path.write_text('{"schema_version":1}')

    with pytest.raises(EvidenceNavigationError, match="changed"):
        _locator().locate_anchor(anchor, context_segments=1)


def test_anchor_reopen_refuses_missing_stored_segment(tmp_path: Path) -> None:
    path = tmp_path / "old-generation.json"
    digest = _write_canonical(path)
    anchor = EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=digest,
        canonical_path=str(path),
        source_path="/recording.wav",
        segment_ids=("segment-missing",),
        start_seconds=2.1,
        end_seconds=2.9,
    )

    with pytest.raises(EvidenceNavigationError, match="no longer available"):
        _locator().locate_anchor(anchor)
