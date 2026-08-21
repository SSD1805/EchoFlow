import pytest
from pydantic import ValidationError

from echoflow.desktop.transcript_tools_bridge import (
    dispatch_transcript_tools,
    handle_request,
)
from echoflow.library.speaker_label_service import SpeakerRosterEntry
from echoflow.library.transcript_tools import (
    TranscriptDetails,
    TranscriptDiarizationDetails,
    TranscriptEngineDetails,
    TranscriptEnhancementDetails,
    TranscriptPublication,
    TranscriptPublicationResult,
    TranscriptToolingSnapshot,
)
from echoflow.transcription.export import TranscriptExportFormat


class ToolingStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def inspect(self, document_id: str, *, expected_canonical_sha256: str):
        self.calls.append(("inspect", (document_id, expected_canonical_sha256)))
        return TranscriptToolingSnapshot(
            details=TranscriptDetails(
                document_id=document_id,
                source_sha256="b" * 64,
                canonical_sha256=expected_canonical_sha256,
                source_available=True,
                source_size_bytes=100,
                source_modified_ns=1,
                container_format="m4a",
                duration_seconds=12.5,
                audio_stream_index=0,
                profile="balanced",
                provisional=False,
                decode_strategy="direct",
                detected_language="en",
                detected_languages=("en",),
                segment_count=3,
                speaker_count=1,
                engine=TranscriptEngineDetails(
                    name="faster-whisper",
                    package_version="1.2.1",
                    model="small",
                    model_revision="rev",
                    device="cpu",
                    compute_type="int8",
                ),
                diarization=TranscriptDiarizationDetails(
                    provider="pyannote.audio",
                    package_version="4.0.0",
                    model="community-1",
                    model_revision="rev",
                    mode="anonymous_turns_v1",
                ),
                enhancement=TranscriptEnhancementDetails(
                    provider="ffmpeg-afftdn",
                    provider_version="7.1",
                    operation="afftdn",
                    model_id=None,
                    model_revision=None,
                ),
            ),
            speakers=(SpeakerRosterEntry("speaker-01", "Interviewer"),),
        )

    def speaker_spans(self, document_id: str, *, expected_canonical_sha256: str):
        self.calls.append(("spans", (document_id, expected_canonical_sha256)))
        return ()

    def set_speaker_label(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        speaker_ref: str,
        label: str,
    ):
        self.calls.append(
            ("set", (document_id, expected_canonical_sha256, speaker_ref, label))
        )
        return SpeakerRosterEntry(speaker_ref, label)

    def remove_speaker_label(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        speaker_ref: str,
    ) -> bool:
        self.calls.append(
            ("remove", (document_id, expected_canonical_sha256, speaker_ref))
        )
        return True

    def publish(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        destination: str,
        formats: tuple[TranscriptExportFormat, ...],
    ):
        self.calls.append(
            (
                "publish",
                (document_id, expected_canonical_sha256, destination, formats),
            )
        )
        return TranscriptPublicationResult(
            canonical_sha256=expected_canonical_sha256,
            publications=tuple(
                TranscriptPublication(format=item, filename=f"interview.{item.value}")
                for item in formats
            ),
        )


def test_inspect_serialization_exposes_details_without_paths() -> None:
    stub = ToolingStub()
    digest = "a" * 64

    result = dispatch_transcript_tools(
        "transcripts.tools.inspect",
        {"document_id": " interview-1 ", "canonical_sha256": digest},
        stub,  # type: ignore[arg-type]
    )

    assert isinstance(result, dict)
    assert result["details"]["canonical_sha256"] == digest  # type: ignore[index]
    assert result["details"]["audio_stream_index"] == 0  # type: ignore[index]
    assert (
        result["speakers"][0]["display_name"]  # type: ignore[index]
        == "Interviewer (speaker-01)"
    )
    assert "path" not in str(result).lower()
    assert stub.calls == [("inspect", ("interview-1", digest))]


def test_set_label_trims_human_input_before_application_call() -> None:
    stub = ToolingStub()
    digest = "a" * 64

    result = dispatch_transcript_tools(
        "transcripts.tools.speaker.set",
        {
            "document_id": "interview-1",
            "canonical_sha256": digest,
            "speaker_ref": " speaker-01 ",
            "label": " Interviewer ",
        },
        stub,  # type: ignore[arg-type]
    )

    assert result["display_label"] == "Interviewer"  # type: ignore[index]
    assert stub.calls[-1] == (
        "set",
        ("interview-1", digest, "speaker-01", "Interviewer"),
    )


@pytest.mark.parametrize(
    "params",
    [
        {"document_id": "x", "canonical_sha256": "A" * 64},
        {"document_id": "x", "canonical_sha256": "a" * 63},
        {"document_id": "", "canonical_sha256": "a" * 64},
        {"document_id": "x", "canonical_sha256": "a" * 64, "extra": True},
    ],
)
def test_inspect_rejects_invalid_or_extra_request_values(
    params: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        dispatch_transcript_tools(
            "transcripts.tools.inspect",
            params,
            ToolingStub(),  # type: ignore[arg-type]
        )


def test_publish_requires_one_to_three_closed_formats() -> None:
    digest = "a" * 64
    stub = ToolingStub()

    result = dispatch_transcript_tools(
        "transcripts.tools.publish",
        {
            "document_id": "interview-1",
            "canonical_sha256": digest,
            "destination": "selected-export-folder",
            "formats": ["txt", "vtt"],
        },
        stub,  # type: ignore[arg-type]
    )

    assert [
        item["format"]
        for item in result["publications"]  # type: ignore[index]
    ] == ["txt", "vtt"]
    with pytest.raises(ValidationError):
        dispatch_transcript_tools(
            "transcripts.tools.publish",
            {
                "document_id": "interview-1",
                "canonical_sha256": digest,
                "destination": "selected-export-folder",
                "formats": [],
            },
            stub,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        dispatch_transcript_tools(
            "transcripts.tools.publish",
            {
                "document_id": "interview-1",
                "canonical_sha256": digest,
                "destination": "selected-export-folder",
                "formats": ["pdf"],
            },
            stub,  # type: ignore[arg-type]
        )


def test_unknown_operation_is_denied_before_service_dispatch() -> None:
    stub = ToolingStub()
    response = handle_request(
        {
            "protocol_version": 1,
            "request_id": "request-1",
            "method": "transcripts.tools.shell",
            "params": {},
        },
        stub,  # type: ignore[arg-type]
    )

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "Transcript-tools request is invalid",
    }
    assert stub.calls == []
