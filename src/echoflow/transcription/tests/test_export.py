from unittest.mock import Mock, call

import pytest

from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.export import (
    TranscriptExporter,
    TranscriptExportError,
    TranscriptExportFormat,
    render_subrip,
    render_text,
    render_webvtt,
)
from echoflow.transcription.models import (
    CanonicalTranscript,
    DecodeStrategy,
    EngineProvenance,
    RecognizedSegment,
    TranscriptSource,
)
from echoflow.workspace.models import Artifact, ArtifactKind, Job, JobId


def transcript(*segments: RecognizedSegment) -> CanonicalTranscript:
    return CanonicalTranscript(
        job_id="job-1",
        source=TranscriptSource(
            sha256="0" * 64,
            size_bytes=10,
            modified_ns=1,
            container_format="wav",
            duration_seconds=8_000,
            audio_stream_index=0,
        ),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=EngineProvenance(
            name="faster-whisper",
            package_version="1.2.1",
            model="small",
            model_revision="revision-1",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            beam_size=5,
            requested_language=None,
        ),
        detected_language="en",
        language_probability=0.99,
        segments=segments,
    )


def test_text_export_is_utf8_canonical_text_with_terminal_newline():
    value = transcript(
        RecognizedSegment(0, 0, 1, "  Hello  "),
        RecognizedSegment(1, 1, 2, "世界"),
    )
    assert render_text(value) == "Hello 世界\n".encode()


def test_subrip_uses_source_relative_timestamps_and_outward_millisecond_rounding():
    value = transcript(
        RecognizedSegment(0, 3_661.0004, 3_662.9991, "first line\nsecond line"),
        RecognizedSegment(1, 7_200, 7_200.0001, "Later"),
    )
    assert render_subrip(value).decode() == (
        "1\n"
        "01:01:01,000 --> 01:01:03,000\n"
        "first line second line\n\n"
        "2\n"
        "02:00:00,000 --> 02:00:00,001\n"
        "Later\n\n"
    )


def test_webvtt_keeps_stable_canonical_segment_ids():
    value = transcript(
        RecognizedSegment(0, 0, 1.25, "Hello"),
        RecognizedSegment(1, 601.5, 602, "After segmentation boundary"),
    )
    assert render_webvtt(value).decode() == (
        "WEBVTT\n\n"
        "segment-000000\n"
        "00:00:00.000 --> 00:00:01.250\n"
        "Hello\n\n"
        "segment-000001\n"
        "00:10:01.500 --> 00:10:02.000\n"
        "After segmentation boundary\n\n"
    )


def test_subtitle_export_rejects_nul_instead_of_writing_invalid_cue():
    value = transcript(RecognizedSegment(0, 0, 1, "unsafe\x00text"))
    with pytest.raises(
        TranscriptExportError,
        match="^Transcript contains text that cannot be exported$",
    ):
        render_webvtt(value)


def test_empty_transcript_has_valid_empty_views():
    value = transcript()
    assert render_text(value) == b"\n"
    assert render_subrip(value) == b""
    assert render_webvtt(value) == b"WEBVTT\n\n"


def test_exporter_renders_before_reserving_and_deduplicates_formats(tmp_path):
    workspace = Mock()
    file_manager = Mock()
    job = Job(
        JobId("job-1"),
        tmp_path / "input.wav",
        tmp_path / "state/jobs/job-1",
        tmp_path / "output",
    )
    text_artifact = Artifact(
        job.job_id, ArtifactKind.TEXT, tmp_path / "output/input.txt"
    )
    srt_artifact = Artifact(
        job.job_id, ArtifactKind.SUBRIP, tmp_path / "output/input.srt"
    )
    workspace.reserve_artifact.side_effect = [text_artifact, srt_artifact]
    exporter = TranscriptExporter(
        workspace_service=workspace, file_manager=file_manager
    )

    result = exporter.publish(
        job,
        transcript(RecognizedSegment(0, 0, 1, "Hello")),
        (
            TranscriptExportFormat.TEXT,
            TranscriptExportFormat.TEXT,
            TranscriptExportFormat.SUBRIP,
        ),
    )

    assert result.artifacts == (text_artifact, srt_artifact)
    assert workspace.reserve_artifact.call_count == 2
    file_manager.save_file.assert_any_call(b"Hello\n", text_artifact.path)
    assert file_manager.save_file.call_count == 2


def test_exporter_rolls_back_entire_derived_set_without_touching_canonical(tmp_path):
    workspace = Mock()
    file_manager = Mock()
    job = Job(
        JobId("job-1"),
        tmp_path / "input.wav",
        tmp_path / "state/jobs/job-1",
        tmp_path / "output",
    )
    text_artifact = Artifact(
        job.job_id, ArtifactKind.TEXT, tmp_path / "output/input.txt"
    )
    vtt_artifact = Artifact(
        job.job_id, ArtifactKind.WEBVTT, tmp_path / "output/input.vtt"
    )
    workspace.reserve_artifact.side_effect = [text_artifact, vtt_artifact]
    file_manager.save_file.side_effect = [None, OSError("disk full")]
    exporter = TranscriptExporter(
        workspace_service=workspace, file_manager=file_manager
    )

    with pytest.raises(OSError, match="disk full"):
        exporter.publish(
            job,
            transcript(RecognizedSegment(0, 0, 1, "Hello")),
            (TranscriptExportFormat.TEXT, TranscriptExportFormat.WEBVTT),
        )

    assert file_manager.delete_file.call_args_list == [
        call(text_artifact.path),
        call(vtt_artifact.path),
    ]
    assert all(
        invoked.args[0].suffix != ".json"
        for invoked in file_manager.delete_file.call_args_list
    )
