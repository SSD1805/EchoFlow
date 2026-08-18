import hashlib
import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import SpeakerLabelStateError
from echoflow.library.index import IndexedDocument
from echoflow.library.speaker_label_service import SpeakerLabelService
from echoflow.library.speaker_labels import SpeakerDisplayLabel, SpeakerLabelStore


class DocumentIndex:
    def __init__(self, documents: tuple[IndexedDocument, ...]) -> None:
        self._documents = documents

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self._documents


def _canonical(path: Path, *, second_word_speaker: str = "speaker-02") -> str:
    document = {
        "schema_version": 1,
        "job_id": "job-1",
        "source": {
            "sha256": "a" * 64,
            "size_bytes": 100,
            "modified_ns": 1,
        },
        "segments": [
            {
                "segment_id": "segment-000000",
                "start_seconds": 1.0,
                "end_seconds": 3.0,
                "text": "Hello there",
                "speaker_ref": "speaker-01",
                "words": [
                    {
                        "start_seconds": 1.0,
                        "end_seconds": 1.5,
                        "text": "Hello",
                        "speaker_ref": "speaker-01",
                    },
                    {
                        "start_seconds": 2.0,
                        "end_seconds": 2.5,
                        "text": " there",
                        "speaker_ref": second_word_speaker,
                    },
                ],
            }
        ],
    }
    payload = json.dumps(document, sort_keys=True).encode()
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
) -> SpeakerLabelService:
    file_manager = LocalFileManager()
    store = SpeakerLabelStore(
        tmp_path / "state" / "library" / "user-state" / "speaker-labels.json",
        file_manager,  # type: ignore[arg-type]
    )
    return SpeakerLabelService(
        index=DocumentIndex((document,)),  # type: ignore[arg-type]
        store=store,
        file_manager=file_manager,  # type: ignore[arg-type]
    )


def test_roster_reads_segment_and_word_only_speaker_evidence(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    document = _document(canonical, _canonical(canonical))
    service = _service(tmp_path, document)

    roster = service.roster("job-1")

    assert [item.speaker_ref for item in roster] == ["speaker-01", "speaker-02"]
    assert [item.display_name for item in roster] == ["speaker-01", "speaker-02"]


def test_label_is_user_state_without_replacing_anonymous_evidence(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    document = _document(canonical, digest)
    service = _service(tmp_path, document)

    binding = service.set_label("job-1", speaker_ref="speaker-02", label="  Dr. Chen  ")
    roster = service.roster("job-1")

    assert binding.label == "Dr. Chen"
    assert roster[1].speaker_ref == "speaker-02"
    assert roster[1].display_label == "Dr. Chen"
    assert roster[1].display_name == "Dr. Chen (speaker-02)"
    assert service.display_labels(
        document_id="job-1",
        canonical_sha256=digest,
        speaker_refs=("speaker-01", "speaker-02"),
    ) == {"speaker-02": "Dr. Chen"}


def test_unknown_speaker_reference_is_rejected(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    document = _document(canonical, _canonical(canonical))
    service = _service(tmp_path, document)

    with pytest.raises(SpeakerLabelStateError, match="not present"):
        service.set_label("job-1", speaker_ref="speaker-99", label="Mystery Guest")


def test_label_does_not_follow_changed_canonical_generation(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    first_digest = _canonical(canonical)
    first = _document(canonical, first_digest)
    service = _service(tmp_path, first)
    service.set_label("job-1", speaker_ref="speaker-02", label="Dr. Chen")

    second_digest = _canonical(canonical, second_word_speaker="speaker-03")
    second = _document(canonical, second_digest)
    current = _service(tmp_path, second)

    assert current.display_labels(
        document_id="job-1",
        canonical_sha256=second_digest,
        speaker_refs=("speaker-02",),
    ) == {}
    views = current.views("job-1")
    assert len(views) == 1
    assert views[0].binding.canonical_sha256 == first_digest
    assert not views[0].current
    assert [item.speaker_ref for item in current.roster("job-1")] == [
        "speaker-01",
        "speaker-03",
    ]


def test_canonical_change_requires_library_rebuild_before_edit(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    document = _document(canonical, _canonical(canonical))
    service = _service(tmp_path, document)
    canonical.write_text('{"segments": []}')

    with pytest.raises(SpeakerLabelStateError, match="rebuild the library"):
        service.set_label("job-1", speaker_ref="speaker-01", label="Interviewer")


def test_replacing_and_removing_label_is_deterministic(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    document = _document(canonical, _canonical(canonical))
    service = _service(tmp_path, document)

    service.set_label("job-1", speaker_ref="speaker-01", label="Interviewer")
    service.set_label("job-1", speaker_ref="speaker-01", label="Host")

    assert service.roster("job-1")[0].display_label == "Host"
    assert service.remove_label("job-1", speaker_ref="speaker-01")
    assert service.roster("job-1")[0].display_label is None
    assert not service.remove_label("job-1", speaker_ref="speaker-01")


def test_corrupt_user_state_fails_closed(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    document = _document(canonical, _canonical(canonical))
    service = _service(tmp_path, document)
    state = tmp_path / "state" / "library" / "user-state" / "speaker-labels.json"
    state.parent.mkdir(parents=True)
    state.write_text("not json")

    with pytest.raises(SpeakerLabelStateError, match="could not be validated"):
        service.roster("job-1")


@pytest.mark.parametrize("label", ["", "   ", "bad\nlabel", "bad\x00label"])
def test_invalid_display_labels_are_rejected(label: str) -> None:
    with pytest.raises(ValueError, match="label"):
        SpeakerDisplayLabel(
            document_id="job-1",
            canonical_sha256="a" * 64,
            speaker_ref="speaker-01",
            label=label,
        )
