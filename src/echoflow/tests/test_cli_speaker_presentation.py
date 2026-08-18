import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.index import IndexedDocument
from echoflow.library.speaker_labels import SpeakerLabelStore


class DocumentIndex:
    def __init__(self, document: IndexedDocument) -> None:
        self.document = document

    def documents(self) -> tuple[IndexedDocument, ...]:
        return (self.document,)


def _app(tmp_path: Path) -> typer.Typer:
    canonical = tmp_path / "transcript.json"
    payload = json.dumps(
        {
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
                    "start_seconds": 0.0,
                    "end_seconds": 2.0,
                    "text": "Excuse me",
                    "speaker_ref": None,
                    "words": [
                        {
                            "start_seconds": 0.9,
                            "end_seconds": 1.1,
                            "text": "Excuse me",
                            "speaker_ref": None,
                        }
                    ],
                }
            ],
            "speaker_turns": [
                {
                    "start_seconds": 0.0,
                    "end_seconds": 1.2,
                    "speaker_ref": "speaker-01",
                },
                {
                    "start_seconds": 0.8,
                    "end_seconds": 1.5,
                    "speaker_ref": "speaker-02",
                },
            ],
        },
        sort_keys=True,
    ).encode()
    canonical.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    document = IndexedDocument(
        document_id="job-1",
        source_sha256="a" * 64,
        detected_language="en",
        canonical_path=str(canonical.resolve()),
        source_path=None,
        segment_count=1,
        canonical_sha256=digest,
    )
    file_manager = LocalFileManager()
    labels = SpeakerLabelStore(
        tmp_path / "state" / "library" / "user-state" / "speaker-labels.json",
        file_manager,  # type: ignore[arg-type]
    )
    labels.set_label(document, speaker_ref="speaker-02", label="Dr. Chen")

    container = Mock()
    container.transcript_index.return_value = DocumentIndex(document)
    container.speaker_label_store.return_value = labels
    container.file_manager.return_value = file_manager
    app = typer.Typer()
    register_library_commands(app, lambda context: container)
    return app


def test_speaker_transcript_human_view_shows_overlap_and_display_label(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        _app(tmp_path), ["library", "speakers", "transcript", "job-1"]
    )

    assert result.exit_code == 0
    assert "00:00:00.900" in result.stdout
    assert "00:00:01.100" in result.stdout
    assert "speaker-01" in result.stdout
    assert "Dr. Chen (speaker-02)" in result.stdout
    assert "overlap" in result.stdout
    assert "Excuse me" in result.stdout


def test_speaker_transcript_json_keeps_raw_refs_labels_and_canonical_binding(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        _app(tmp_path),
        ["library", "speakers", "transcript", "job-1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    span = payload[0]
    assert span["kind"] == "overlap"
    assert span["overlap"] is True
    assert span["start_seconds"] == 0.9
    assert span["start_timestamp"] == "00:00:00.900"
    assert span["end_timestamp"] == "00:00:01.100"
    assert len(span["canonical_sha256"]) == 64
    assert span["speakers"] == [
        {
            "display_label": None,
            "display_name": "speaker-01",
            "speaker_ref": "speaker-01",
        },
        {
            "display_label": "Dr. Chen",
            "display_name": "Dr. Chen (speaker-02)",
            "speaker_ref": "speaker-02",
        },
    ]
