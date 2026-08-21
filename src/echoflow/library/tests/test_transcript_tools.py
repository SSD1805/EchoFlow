import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import TranscriptToolingError
from echoflow.library.index import IndexedDocument
from echoflow.library.speaker_label_service import SpeakerLabelService
from echoflow.library.speaker_labels import SpeakerLabelStore
from echoflow.library.speaker_presentation import SpeakerPresentationService
from echoflow.library.transcript_tools import TranscriptToolsService
from echoflow.transcription.export import TranscriptExportFormat


class DocumentIndex:
    def __init__(self, documents: tuple[IndexedDocument, ...]) -> None:
        self._documents = documents

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self._documents


def _canonical(path: Path, *, speaker: str = "speaker-01") -> str:
    document = {
        "schema_version": 1,
        "job_id": "job-1",
        "source": {
            "sha256": "a" * 64,
            "size_bytes": 1234,
            "modified_ns": 42,
            "container_format": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration_seconds": 8.5,
            "audio_stream_index": 2,
        },
        "profile": "balanced",
        "provisional": False,
        "decode_strategy": "ffmpeg_normalize",
        "engine": {
            "name": "faster-whisper",
            "package_version": "1.2.1",
            "model": "small",
            "model_revision": "rev-1",
            "device": "cpu",
            "compute_type": "int8",
        },
        "detected_language": "en",
        "detected_languages": ["en"],
        "segments": [
            {
                "segment_id": "segment-000000",
                "start_seconds": 1.0,
                "end_seconds": 3.0,
                "text": "Hello there",
                "speaker_ref": speaker,
                "words": [
                    {
                        "start_seconds": 1.0,
                        "end_seconds": 1.5,
                        "text": "Hello",
                        "speaker_ref": speaker,
                    },
                    {
                        "start_seconds": 1.6,
                        "end_seconds": 2.2,
                        "text": " there",
                        "speaker_ref": speaker,
                    },
                ],
            },
            {
                "segment_id": "segment-000001",
                "start_seconds": 3.2,
                "end_seconds": 5.0,
                "text": "Second line",
                "speaker_ref": "speaker-02",
                "words": [],
            },
        ],
        "diarization": {
            "provider": "pyannote.audio",
            "package_version": "4.0.0",
            "model": "speaker-diarization-community-1",
            "model_revision": "model-rev",
            "mode": "anonymous_turns_v1",
            "telemetry_enabled": False,
        },
        "speaker_turns": [
            {"start_seconds": 0.9, "end_seconds": 3.1, "speaker_ref": speaker},
            {"start_seconds": 3.2, "end_seconds": 5.0, "speaker_ref": "speaker-02"},
        ],
        "enhancement": {
            "schema_version": 1,
            "provider": "ffmpeg-afftdn",
            "provider_version": "7.1",
            "operation": "afftdn",
            "parameters": {"nr": "12"},
            "model_id": None,
            "model_revision": None,
        },
    }
    payload = json.dumps(document, sort_keys=True).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _service(
    tmp_path: Path, *, source_exists: bool = True
) -> tuple[TranscriptToolsService, str]:
    canonical = tmp_path / "interview.json"
    digest = _canonical(canonical)
    source = tmp_path / "interview.m4a"
    if source_exists:
        source.write_bytes(b"media")
    document = IndexedDocument(
        document_id="job-1",
        source_sha256="a" * 64,
        detected_language="en",
        canonical_path=str(canonical.resolve()),
        source_path=str(source.resolve()),
        segment_count=2,
        canonical_sha256=digest,
    )
    index = DocumentIndex((document,))
    files = LocalFileManager()
    labels = SpeakerLabelStore(
        tmp_path / "speaker-labels.json",
        files,  # type: ignore[arg-type]
    )
    label_service = SpeakerLabelService(
        index=index,  # type: ignore[arg-type]
        store=labels,
        file_manager=files,  # type: ignore[arg-type]
    )
    presentation = SpeakerPresentationService(
        index=index,  # type: ignore[arg-type]
        label_store=labels,
        file_manager=files,  # type: ignore[arg-type]
    )
    return (
        TranscriptToolsService(
            index=index,  # type: ignore[arg-type]
            speaker_labels=label_service,
            speaker_presentation=presentation,
            file_manager=files,  # type: ignore[arg-type]
        ),
        digest,
    )


def test_inspect_returns_verified_details_and_current_roster(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)

    snapshot = service.inspect("job-1", expected_canonical_sha256=digest)

    assert snapshot.details.canonical_sha256 == digest
    assert snapshot.details.source_sha256 == "a" * 64
    assert snapshot.details.source_available
    assert snapshot.details.audio_stream_index == 2
    assert snapshot.details.profile == "balanced"
    assert snapshot.details.engine.model == "small"
    assert snapshot.details.diarization is not None
    assert snapshot.details.enhancement is not None
    assert snapshot.details.segment_count == 2
    assert snapshot.details.speaker_count == 2
    assert [speaker.speaker_ref for speaker in snapshot.speakers] == [
        "speaker-01",
        "speaker-02",
    ]


def test_inspect_reports_missing_source_without_invalidating_canonical_evidence(
    tmp_path: Path,
) -> None:
    service, digest = _service(tmp_path, source_exists=False)

    snapshot = service.inspect("job-1", expected_canonical_sha256=digest)

    assert not snapshot.details.source_available
    assert snapshot.details.canonical_sha256 == digest


def test_generation_guard_rejects_stale_desktop_mutation(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(
        TranscriptToolingError, match="changed since this view was opened"
    ):
        service.set_speaker_label(
            "job-1",
            expected_canonical_sha256="b" * 64,
            speaker_ref="speaker-01",
            label="Interviewer",
        )


def test_label_mutation_preserves_anonymous_ref_and_can_be_removed(
    tmp_path: Path,
) -> None:
    service, digest = _service(tmp_path)

    named = service.set_speaker_label(
        "job-1",
        expected_canonical_sha256=digest,
        speaker_ref="speaker-01",
        label=" Interviewer ",
    )
    snapshot = service.inspect("job-1", expected_canonical_sha256=digest)

    assert named.speaker_ref == "speaker-01"
    assert named.display_label == "Interviewer"
    assert snapshot.speakers[0].display_name == "Interviewer (speaker-01)"
    assert service.remove_speaker_label(
        "job-1",
        expected_canonical_sha256=digest,
        speaker_ref="speaker-01",
    )
    assert (
        service.inspect("job-1", expected_canonical_sha256=digest)
        .speakers[0]
        .display_label
        is None
    )


def test_speaker_presentation_is_generation_bound(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)

    spans = service.speaker_spans("job-1", expected_canonical_sha256=digest)

    assert spans
    assert {span.canonical_sha256 for span in spans} == {digest}
    assert {speaker.speaker_ref for span in spans for speaker in span.speakers} == {
        "speaker-01",
        "speaker-02",
    }


def test_publish_is_deterministic_deduplicated_and_collision_safe(
    tmp_path: Path,
) -> None:
    service, digest = _service(tmp_path)
    destination = tmp_path / "exports"
    destination.mkdir()
    (destination / "interview.txt").write_text("do not overwrite")

    result = service.publish(
        "job-1",
        expected_canonical_sha256=digest,
        destination=destination,
        formats=(
            TranscriptExportFormat.TEXT,
            TranscriptExportFormat.TEXT,
            TranscriptExportFormat.WEBVTT,
        ),
    )

    assert [item.filename for item in result.publications] == [
        "interview-2.txt",
        "interview.vtt",
    ]
    assert (destination / "interview.txt").read_text() == "do not overwrite"
    assert (destination / "interview-2.txt").read_text() == (
        "[speaker-01] Hello there\n[speaker-02] Second line\n"
    )
    assert (destination / "interview.vtt").read_text().startswith("WEBVTT\n\n")
    assert str(destination) not in " ".join(
        item.filename for item in result.publications
    )


def test_publish_rejects_empty_formats_and_missing_destination(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)

    with pytest.raises(ValueError, match="at least one"):
        service.publish(
            "job-1",
            expected_canonical_sha256=digest,
            destination=tmp_path,
            formats=(),
        )
    with pytest.raises(TranscriptToolingError, match="not an available folder"):
        service.publish(
            "job-1",
            expected_canonical_sha256=digest,
            destination=tmp_path / "missing",
            formats=(TranscriptExportFormat.TEXT,),
        )


def test_tampered_canonical_is_rejected_even_when_index_generation_is_stale(
    tmp_path: Path,
) -> None:
    service, digest = _service(tmp_path)
    canonical = tmp_path / "interview.json"
    canonical.write_text("{}")

    with pytest.raises(TranscriptToolingError, match="Canonical transcript changed"):
        service.inspect("job-1", expected_canonical_sha256=digest)


@given(
    st.text(min_size=0, max_size=80).filter(
        lambda value: (
            not (
                len(value) == 64
                and all(character in "0123456789abcdef" for character in value)
            )
        )
    )
)
def test_generation_guard_rejects_noncanonical_digest_shapes(value: str) -> None:
    with TemporaryDirectory() as directory:
        service, _ = _service(Path(directory))

        with pytest.raises(ValueError, match="expected_canonical_sha256"):
            service.inspect("job-1", expected_canonical_sha256=value)
