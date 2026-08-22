import json
from unittest.mock import Mock

from scholion.transcription.speaker_models import (
    DiarizationProvenance,
    SpeakerDiarizationRequest,
    SpeakerDiarizationResult,
    SpeakerTurn,
)
from scholion.transcription.tests.test_executor import executor, plan


def test_executor_diarizes_canonical_audio_and_publishes_current_schema(tmp_path):
    planned, paths = plan(tmp_path)
    (
        service,
        _probe,
        _inspector,
        decoder,
        _segmenter,
        _transcriber,
        _session,
        _logger,
        _materialized,
    ) = executor(tmp_path, planned, paths)
    diarizer = Mock()
    diarizer.diarize.return_value = SpeakerDiarizationResult(
        turns=(
            SpeakerTurn(0.0, 1.0, "speaker-01"),
            SpeakerTurn(1.0, 2.0, "speaker-02"),
        ),
        provenance=DiarizationProvenance(
            provider="pyannote.audio",
            package_version="4.0.7",
            model="pyannote/speaker-diarization-community-1",
            model_revision="revision-1",
        ),
    )
    service.speaker_diarizer = diarizer
    request = SpeakerDiarizationRequest(num_speakers=2)

    result = service.execute(
        planned,
        allow_diarization_model_download=True,
        diarization_request=request,
    )

    diarizer.diarize.assert_called_once_with(
        decoder.decode.return_value.path,
        allow_model_download=True,
        request=request,
    )
    assert result.transcript.schema_version == 1
    assert [segment.speaker_ref for segment in result.transcript.segments] == [
        "speaker-01",
        "speaker-02",
    ]
    document = json.loads(result.artifact.path.read_text())
    assert document["schema_version"] == 1
    assert document["speaker_turns"] == [
        {
            "end_seconds": 1.0,
            "speaker_ref": "speaker-01",
            "start_seconds": 0.0,
        },
        {
            "end_seconds": 2.0,
            "speaker_ref": "speaker-02",
            "start_seconds": 1.0,
        },
    ]
    assert document["diarization"]["provider"] == "pyannote.audio"
    assert document["diarization"]["telemetry_enabled"] is False
