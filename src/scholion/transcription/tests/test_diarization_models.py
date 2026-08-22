import pytest

from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from scholion.runner.models import ProcessingProfile
from scholion.transcription.models import (
    CanonicalTranscript,
    DecodeStrategy,
    EngineProvenance,
    RecognizedSegment,
    TranscriptSource,
)
from scholion.transcription.speaker_models import DiarizationProvenance, SpeakerTurn


def _source(tmp_path):
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio")
    media = MediaInfo(
        InputIdentity(path.resolve(), 5, path.stat().st_mtime_ns, "0" * 64),
        "wav",
        10.0,
        (MediaStream(0, StreamKind.AUDIO, "pcm_s16le", 10.0, 16_000, 1),),
        0,
    )
    return TranscriptSource.from_media(media)


def _engine():
    return EngineProvenance(
        name="faster-whisper",
        package_version="1.2.1",
        model="tiny",
        model_revision="revision-1",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        beam_size=1,
        requested_language=None,
    )


def _provenance():
    return DiarizationProvenance(
        provider="pyannote.audio",
        package_version="4.0.0",
        model="pyannote/speaker-diarization-community-1",
        model_revision=None,
    )


def test_current_schema_serializes_exact_speaker_turn_evidence(tmp_path):
    transcript = CanonicalTranscript(
        job_id="job-1",
        source=_source(tmp_path),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=_engine(),
        detected_language="en",
        language_probability=None,
        segments=(RecognizedSegment(0, 0.0, 2.0, "hello", speaker_ref="speaker-01"),),
        speaker_turns=(SpeakerTurn(0.0, 2.0, "speaker-01"),),
        diarization=_provenance(),
    )

    document = transcript.to_dict()
    assert document["schema_version"] == 1
    assert document["speaker_turns"] == [
        {"start_seconds": 0.0, "end_seconds": 2.0, "speaker_ref": "speaker-01"}
    ]
    assert document["diarization"]["provider"] == "pyannote.audio"
    assert document["diarization"]["telemetry_enabled"] is False


def test_current_schema_allows_absent_diarization_evidence(tmp_path):
    transcript = CanonicalTranscript(
        job_id="job-1",
        source=_source(tmp_path),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=_engine(),
        detected_language=None,
        language_probability=None,
        segments=(),
    )

    document = transcript.to_dict()
    assert document["schema_version"] == 1
    assert document["speaker_turns"] == []
    assert document["diarization"] is None


def test_current_schema_refuses_turns_outside_source_duration(tmp_path):
    with pytest.raises(ValueError, match="source duration"):
        CanonicalTranscript(
            job_id="job-1",
            source=_source(tmp_path),
            profile=ProcessingProfile.BALANCED,
            provisional=False,
            decode_strategy=DecodeStrategy.DIRECT,
            engine=_engine(),
            detected_language=None,
            language_probability=None,
            segments=(),
            speaker_turns=(SpeakerTurn(9.0, 11.0, "speaker-01"),),
            diarization=_provenance(),
        )
