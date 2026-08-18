import hashlib
import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import SpeakerLabelStateError
from echoflow.library.index import IndexedDocument
from echoflow.library.speaker_labels import SpeakerLabelStore
from echoflow.library.speaker_presentation import (
    SpeakerPresentationKind,
    SpeakerPresentationService,
)


class DocumentIndex:
    def __init__(self, document: IndexedDocument) -> None:
        self.document = document

    def documents(self) -> tuple[IndexedDocument, ...]:
        return (self.document,)


def _write_canonical(
    path: Path,
    *,
    segments: list[dict[str, object]],
    turns: list[dict[str, object]],
) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "job_id": "job-1",
            "source": {
                "sha256": "a" * 64,
                "size_bytes": 100,
                "modified_ns": 1,
            },
            "segments": segments,
            "speaker_turns": turns,
        },
        sort_keys=True,
    ).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _document(path: Path, digest: str) -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256="a" * 64,
        detected_language="en",
        canonical_path=str(path.resolve()),
        source_path=None,
        segment_count=1,
        canonical_sha256=digest,
    )


def _service(
    tmp_path: Path,
    document: IndexedDocument,
) -> tuple[SpeakerPresentationService, SpeakerLabelStore]:
    file_manager = LocalFileManager()
    store = SpeakerLabelStore(
        tmp_path / "state" / "library" / "user-state" / "speaker-labels.json",
        file_manager,  # type: ignore[arg-type]
    )
    service = SpeakerPresentationService(
        index=DocumentIndex(document),  # type: ignore[arg-type]
        label_store=store,
        file_manager=file_manager,  # type: ignore[arg-type]
    )
    return service, store


def _aligned_segment(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "segment_id": "segment-000000",
        "start_seconds": 0.0,
        "end_seconds": 3.0,
        "text": "Hello yes absolutely",
        "speaker_ref": None,
        "words": words,
    }


def test_word_handoff_becomes_readable_spans_with_durable_display_labels(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            _aligned_segment(
                [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 0.8,
                        "text": "Hello",
                        "speaker_ref": "speaker-01",
                    },
                    {
                        "start_seconds": 0.8,
                        "end_seconds": 1.2,
                        "text": " yes",
                        "speaker_ref": "speaker-02",
                    },
                    {
                        "start_seconds": 1.2,
                        "end_seconds": 1.8,
                        "text": " absolutely",
                        "speaker_ref": "speaker-02",
                    },
                ]
            )
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 0.8, "speaker_ref": "speaker-01"},
            {"start_seconds": 0.8, "end_seconds": 2.0, "speaker_ref": "speaker-02"},
        ],
    )
    document = _document(canonical, digest)
    service, labels = _service(tmp_path, document)
    labels.set_label(document, speaker_ref="speaker-01", label="Interviewer")
    labels.set_label(document, speaker_ref="speaker-02", label="Dr. Chen")

    spans = service.spans("job-1")

    assert len(spans) == 2
    assert spans[0].text == "Hello"
    assert spans[0].kind is SpeakerPresentationKind.SINGLE
    assert spans[0].speakers[0].display_name == "Interviewer (speaker-01)"
    assert spans[1].text == "yes absolutely"
    assert spans[1].kind is SpeakerPresentationKind.SINGLE
    assert spans[1].speakers[0].display_name == "Dr. Chen (speaker-02)"
    assert spans[1].start_seconds == 0.8
    assert spans[1].end_seconds == 1.8


def test_simultaneous_turns_are_exposed_as_overlap_without_assigning_one_voice(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            _aligned_segment(
                [
                    {
                        "start_seconds": 0.9,
                        "end_seconds": 1.1,
                        "text": "sorry",
                        "speaker_ref": None,
                    }
                ]
            )
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 1.2, "speaker_ref": "speaker-01"},
            {"start_seconds": 0.8, "end_seconds": 1.5, "speaker_ref": "speaker-02"},
        ],
    )
    document = _document(canonical, digest)
    service, labels = _service(tmp_path, document)
    labels.set_label(document, speaker_ref="speaker-02", label="Dr. Chen")

    span = service.spans("job-1")[0]

    assert span.kind is SpeakerPresentationKind.OVERLAP
    assert span.overlap
    assert [speaker.speaker_ref for speaker in span.speakers] == [
        "speaker-01",
        "speaker-02",
    ]
    assert [speaker.display_name for speaker in span.speakers] == [
        "speaker-01",
        "Dr. Chen (speaker-02)",
    ]
    assert span.text == "sorry"


def test_unattributed_word_is_not_upgraded_from_single_active_turn(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            _aligned_segment(
                [
                    {
                        "start_seconds": 0.2,
                        "end_seconds": 0.5,
                        "text": "uncertain",
                        "speaker_ref": None,
                    }
                ]
            )
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 1.0, "speaker_ref": "speaker-01"}
        ],
    )
    service, _ = _service(tmp_path, _document(canonical, digest))

    span = service.spans("job-1")[0]

    assert span.kind is SpeakerPresentationKind.UNATTRIBUTED
    assert span.speakers == ()


def test_unaligned_sequential_speakers_are_mixed_not_false_overlap(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            {
                "segment_id": "segment-000000",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "text": "A coarse segment with a handoff",
                "speaker_ref": None,
            }
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 1.0, "speaker_ref": "speaker-01"},
            {"start_seconds": 1.0, "end_seconds": 2.0, "speaker_ref": "speaker-02"},
        ],
    )
    service, _ = _service(tmp_path, _document(canonical, digest))

    span = service.spans("job-1")[0]

    assert span.kind is SpeakerPresentationKind.MIXED_UNRESOLVED
    assert not span.overlap
    assert [speaker.speaker_ref for speaker in span.speakers] == [
        "speaker-01",
        "speaker-02",
    ]


def test_unaligned_simultaneous_speakers_are_marked_overlap(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            {
                "segment_id": "segment-000000",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "text": "A coarse overlapping segment",
                "speaker_ref": None,
            }
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 1.5, "speaker_ref": "speaker-01"},
            {"start_seconds": 1.0, "end_seconds": 2.0, "speaker_ref": "speaker-02"},
        ],
    )
    service, _ = _service(tmp_path, _document(canonical, digest))

    span = service.spans("job-1")[0]

    assert span.kind is SpeakerPresentationKind.OVERLAP
    assert span.overlap


def test_changed_canonical_generation_fails_closed(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _write_canonical(
        canonical,
        segments=[
            {
                "segment_id": "segment-000000",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "text": "Hello",
                "speaker_ref": "speaker-01",
            }
        ],
        turns=[
            {"start_seconds": 0.0, "end_seconds": 1.0, "speaker_ref": "speaker-01"}
        ],
    )
    service, _ = _service(tmp_path, _document(canonical, digest))
    canonical.write_text('{"segments": []}')

    with pytest.raises(SpeakerLabelStateError, match="rebuild the library"):
        service.spans("job-1")
