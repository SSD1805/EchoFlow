from types import SimpleNamespace
from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import EvidenceContextSegment, EvidenceWord


class _UnusedLocationService:
    pass


class _Workspace:
    def __init__(self) -> None:
        self.open_call: tuple[str, int] | None = None

    def open_note_evidence(self, note_id: str, *, context_segments: int):
        self.open_call = (note_id, context_segments)
        word = EvidenceWord(
            segment_id="segment-3",
            word_index=0,
            start_seconds=128.4,
            end_seconds=128.7,
            text="Earlier",
            speaker_ref="speaker-old",
        )
        segment = EvidenceContextSegment(
            segment_id="segment-3",
            start_seconds=128.4,
            end_seconds=135.2,
            text="Earlier verified evidence.",
            speaker_refs=("speaker-old",),
            words=(word,),
            is_result_segment=True,
            lexical_match=False,
        )
        evidence = SimpleNamespace(
            document_id="interview-11",
            source_sha256="d" * 64,
            canonical_sha256="c" * 64,
            canonical_path="/sensitive/old.json",
            source_path="/sensitive/interview.wav",
            result_segment_ids=("segment-3",),
            start_seconds=128.4,
            end_seconds=135.2,
            seek_seconds=128.4,
            result_speaker_refs=("speaker-old",),
            matched_words=(),
            context_segments=(segment,),
        )
        return SimpleNamespace(
            note=SimpleNamespace(
                note=SimpleNamespace(note_id="note-older"),
                current=False,
                tags=("review",),
                collections=("Field notes",),
            ),
            located=SimpleNamespace(
                evidence=evidence,
                speakers=(
                    SimpleNamespace(
                        speaker_ref="speaker-old",
                        display_label="Earlier participant",
                    ),
                ),
            ),
        )


def _services(workspace: _Workspace) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, workspace),
        processing=cast(Any, object()),
    )


def _request(method: str, params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "research-note-1",
        "method": method,
        "params": params,
    }


def test_note_evidence_reopens_exact_generation_without_paths() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.evidence",
            {"note_id": "note-older", "context_segments": 1},
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.open_call == ("note-older", 1)
    result = response["result"]
    assert result["current"] is False
    assert result["evidence"]["canonical_sha256"] == "c" * 64
    assert result["evidence"]["text"] == "Earlier verified evidence."
    assert "/sensitive" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_note_evidence_rejects_sql_shaped_extra_params() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.evidence",
            {
                "note_id": "note-older",
                "context_segments": 1,
                "sql": "SELECT * FROM notes",
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"
    assert workspace.open_call is None
