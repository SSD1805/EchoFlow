import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from dependency_injector import providers

from echoflow.app.app_container import AppContainer
from echoflow.core.config import AppConfig
from echoflow.media.models import StreamKind
from echoflow.media.probe import FfprobeMediaProbe
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.audio import FfmpegAudioDecoder
from echoflow.transcription.export import TranscriptExportFormat
from echoflow.transcription.models import (
    DecodeConfiguration,
    DecodeStrategy,
    EngineTranscript,
    RecognizedSegment,
    SegmentationConfiguration,
)
from echoflow.transcription.segmentation import WaveAudioSegmenter


def _native_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"{name} is not installed")
    return executable


def _make_video(path: Path) -> None:
    ffmpeg = _native_tool("ffmpeg")
    command = [
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:r=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-t",
        "2.25",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        "-y",
        str(path),
    ]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603


class _AcceptanceSession:
    engine_version = "acceptance-fake-asr-1"

    def transcribe(self, audio_path: Path) -> EngineTranscript:
        with wave.open(str(audio_path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        return EngineTranscript(
            segments=(
                RecognizedSegment(
                    index=0,
                    start_seconds=0.0,
                    end_seconds=duration,
                    text="Synthetic segment.",
                ),
            ),
            language="en",
            language_probability=1.0,
            engine_version=self.engine_version,
        )


class _AcceptanceTranscriber:
    def open_session(self, _configuration) -> _AcceptanceSession:
        return _AcceptanceSession()


class _ManagedModelRegistry:
    def resolved_revision(self, model_id: str) -> str:
        assert model_id == "tiny"
        return "revision-1"


def _acceptance_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        APP_ENV="test",
        DEBUG=False,
        LOG_LEVEL="INFO",
        STATE_DIR=tmp_path / "state",
        CACHE_DIR=tmp_path / "cache",
        MODEL_DIR=tmp_path / "cache" / "models",
        OUTPUT_DIR=tmp_path / "output",
        MIN_FREE_DISK_BYTES=0,
        WARN_FREE_DISK_BYTES=0,
        FFMPEG_TIMEOUT_SECONDS=2.0,
        FFPROBE_TIMEOUT_SECONDS=10.0,
        FFMPEG_PROCESS_TIMEOUT_SECONDS=30.0,
        _env_file=None,
    )


def test_real_ffmpeg_video_probe_decode_and_segment_pipeline(tmp_path):
    _native_tool("ffprobe")
    source = tmp_path / "synthetic-interview.mp4"
    workspace = tmp_path / "private-job"
    workspace.mkdir()
    _make_video(source)

    media = FfprobeMediaProbe().probe(source)
    assert any(stream.kind is StreamKind.VIDEO for stream in media.streams)
    assert media.primary_audio_stream.kind is StreamKind.AUDIO
    assert media.primary_audio_stream.codec == "aac"

    decoder_config = DecodeConfiguration(
        DecodeStrategy.FFMPEG_NORMALIZE,
        "pcm_s16le",
        16_000,
        1,
    )
    decoder = FfmpegAudioDecoder()
    decoded = decoder.decode(media, decoder_config, workspace)
    assert decoded.temporary is True
    assert decoded.path == workspace / "normalized.wav"

    with wave.open(str(decoded.path), "rb") as normalized:
        assert normalized.getframerate() == 16_000
        assert normalized.getnchannels() == 1
        assert normalized.getsampwidth() == 2
        assert normalized.getnframes() > 32_000

    segmenter = WaveAudioSegmenter()
    windows = segmenter.plan(
        decoded.path,
        decoder_config,
        SegmentationConfiguration(segment_duration_seconds=1),
    )
    assert len(windows) >= 3
    assert windows[0].start_frame == 0
    assert all(
        current.start_frame == previous.end_frame
        for previous, current in zip(windows, windows[1:], strict=False)
    )

    materialized = segmenter.materialize(
        decoded.path,
        windows[1],
        decoder_config,
        workspace,
    )
    with wave.open(str(materialized.path), "rb") as segment:
        assert segment.getnframes() == windows[1].end_frame - windows[1].start_frame
        assert segment.getframerate() == 16_000
        assert segment.getnchannels() == 1

    segmenter.cleanup(materialized)
    assert not materialized.path.exists()
    decoder.cleanup(decoded)
    assert not decoded.path.exists()
    assert source.exists()


def test_real_local_pipeline_publishes_and_cleans_up_with_only_asr_faked(tmp_path):
    _native_tool("ffprobe")
    source = tmp_path / "synthetic-research-interview.mp4"
    _make_video(source)

    container = AppContainer()
    container.config.override(_acceptance_config(tmp_path))
    container.model_manager.override(providers.Object(_ManagedModelRegistry()))
    container.transcriber.override(providers.Factory(_AcceptanceTranscriber))

    plan = container.transcription_planner().plan(
        source,
        profile=ProcessingProfile.SCREENING,
    )
    result = container.transcription_executor().execute(plan)

    assert source.exists()
    assert result.artifact.path.is_file()
    canonical = json.loads(result.artifact.path.read_text(encoding="utf-8"))
    assert canonical["job_id"] == result.job.job_id.value
    assert canonical["text"] == "Synthetic segment."
    assert canonical["engine"]["package_version"] == "acceptance-fake-asr-1"
    assert canonical["engine"]["model_revision"] == "revision-1"

    assert not (result.job.workspace_dir / "normalized.wav").exists()
    assert not tuple(result.job.workspace_dir.glob("audio-*.wav"))
    checkpoint_dir = result.job.workspace_dir / "checkpoints"
    assert checkpoint_dir.is_dir()
    assert list(checkpoint_dir.iterdir()) == []

    exports = container.transcript_exporter().publish(
        result.job,
        result.transcript,
        (
            TranscriptExportFormat.TEXT,
            TranscriptExportFormat.SUBRIP,
            TranscriptExportFormat.WEBVTT,
        ),
    )
    by_kind = {artifact.kind.value: artifact.path for artifact in exports.artifacts}
    assert by_kind["txt"].read_text(encoding="utf-8") == "Synthetic segment.\n"
    assert "00:00:00,000 -->" in by_kind["srt"].read_text(encoding="utf-8")
    assert by_kind["vtt"].read_text(encoding="utf-8").startswith("WEBVTT\n\n")
