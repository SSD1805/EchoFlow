from scholion.runner.models import ProcessingProfile
from scholion.transcription.export import render_subrip, render_text, render_webvtt
from scholion.transcription.models import (
    CanonicalTranscript,
    DecodeStrategy,
    EngineProvenance,
    RecognizedSegment,
    TranscriptSource,
)
from scholion.transcription.speaker_models import DiarizationProvenance, SpeakerTurn


def _transcript() -> CanonicalTranscript:
    return CanonicalTranscript(
        job_id="job-1",
        source=TranscriptSource(
            sha256="0" * 64,
            size_bytes=10,
            modified_ns=1,
            container_format="wav",
            duration_seconds=10,
            audio_stream_index=0,
        ),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=EngineProvenance(
            name="faster-whisper",
            package_version="1.2.1",
            model="tiny",
            model_revision="revision-1",
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            beam_size=1,
            requested_language=None,
        ),
        detected_language="en",
        language_probability=None,
        segments=(
            RecognizedSegment(0, 0.0, 1.0, "Hello", speaker_ref="speaker-01"),
            RecognizedSegment(1, 1.0, 2.0, "handoff"),
            RecognizedSegment(2, 2.0, 3.0, "Hi there", speaker_ref="speaker-02"),
        ),
        speaker_turns=(
            SpeakerTurn(0.0, 1.0, "speaker-01"),
            SpeakerTurn(2.0, 3.0, "speaker-02"),
        ),
        diarization=DiarizationProvenance(
            provider="pyannote.audio",
            package_version="4.0.7",
            model="pyannote/speaker-diarization-community-1",
            model_revision="revision-1",
        ),
    )


def test_diarized_text_export_labels_only_unambiguous_segments():
    assert render_text(_transcript()).decode() == (
        "[speaker-01] Hello\nhandoff\n[speaker-02] Hi there\n"
    )


def test_diarized_subtitles_preserve_speaker_labels_without_changing_timestamps():
    subrip = render_subrip(_transcript()).decode()
    webvtt = render_webvtt(_transcript()).decode()
    assert "00:00:00,000 --> 00:00:01,000\n[speaker-01] Hello" in subrip
    assert "00:00:01,000 --> 00:00:02,000\nhandoff" in subrip
    assert "00:00:02.000 --> 00:00:03.000\n[speaker-02] Hi there" in webvtt
