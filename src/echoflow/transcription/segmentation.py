from __future__ import annotations

import wave
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from echoflow.transcription.errors import TranscriptionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    DecodeConfiguration,
    SegmentationConfiguration,
)

_FRAMES_PER_READ = 32_768
_SUPPORTED_CODEC = "pcm_s16le"
_SUPPORTED_SAMPLE_WIDTH_BYTES = 2


@dataclass(frozen=True, slots=True)
class MaterializedAudioSegment:
    window: AudioSegmentWindow
    path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.expanduser().resolve(strict=False))


class WaveAudioSegmenter:
    """Split canonical PCM WAV audio into exact, source-relative frame windows."""

    def plan(
        self,
        audio_path: Path,
        decoder: DecodeConfiguration,
        configuration: SegmentationConfiguration,
    ) -> tuple[AudioSegmentWindow, ...]:
        try:
            with wave.open(str(audio_path), "rb") as source:
                self._validate_source(source, decoder)
                frame_count = source.getnframes()
        except TranscriptionError:
            raise
        except (OSError, wave.Error) as exc:
            raise TranscriptionError(
                "Decoded audio could not be read as canonical WAV", cause=exc
            ) from exc

        if frame_count < 1:
            raise TranscriptionError("Decoded audio contains no usable PCM frames")

        frames_per_segment = (
            configuration.segment_duration_seconds * decoder.sample_rate_hz
        )
        windows: list[AudioSegmentWindow] = []
        start_frame = 0
        while start_frame < frame_count:
            end_frame = min(start_frame + frames_per_segment, frame_count)
            windows.append(
                AudioSegmentWindow(
                    index=len(windows),
                    start_frame=start_frame,
                    end_frame=end_frame,
                    sample_rate_hz=decoder.sample_rate_hz,
                )
            )
            start_frame = end_frame
        return tuple(windows)

    def materialize(
        self,
        audio_path: Path,
        window: AudioSegmentWindow,
        decoder: DecodeConfiguration,
        workspace_dir: Path,
    ) -> MaterializedAudioSegment:
        segment_dir = (workspace_dir / "segments").resolve(strict=False)
        segment_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = segment_dir / f"{window.segment_id}.wav"

        try:
            with wave.open(str(audio_path), "rb") as source:
                self._validate_source(source, decoder)
                if window.sample_rate_hz != source.getframerate():
                    raise TranscriptionError(
                        "Audio segment window does not match decoded sample rate"
                    )
                if window.end_frame > source.getnframes():
                    raise TranscriptionError(
                        "Audio segment window exceeds decoded audio length"
                    )
                source.setpos(window.start_frame)
                self._write_segment(source, destination, window, decoder)
        except TranscriptionError:
            destination.unlink(missing_ok=True)
            raise
        except (OSError, wave.Error) as exc:
            destination.unlink(missing_ok=True)
            raise TranscriptionError(
                "Audio segment could not be materialized", cause=exc
            ) from exc

        return MaterializedAudioSegment(window=window, path=destination)

    @staticmethod
    def cleanup(segment: MaterializedAudioSegment) -> None:
        with suppress(OSError):
            segment.path.unlink(missing_ok=True)

    @staticmethod
    def _validate_source(
        source: wave.Wave_read, decoder: DecodeConfiguration
    ) -> None:
        if decoder.output_codec != _SUPPORTED_CODEC:
            raise TranscriptionError(
                "Segmentation requires the planned canonical PCM codec"
            )
        if (
            source.getcomptype() != "NONE"
            or source.getsampwidth() != _SUPPORTED_SAMPLE_WIDTH_BYTES
            or source.getframerate() != decoder.sample_rate_hz
            or source.getnchannels() != decoder.channels
        ):
            raise TranscriptionError(
                "Decoded audio does not match the planned canonical PCM format"
            )

    @staticmethod
    def _write_segment(
        source: wave.Wave_read,
        destination: Path,
        window: AudioSegmentWindow,
        decoder: DecodeConfiguration,
    ) -> None:
        remaining_frames = window.end_frame - window.start_frame
        frame_width = decoder.channels * _SUPPORTED_SAMPLE_WIDTH_BYTES
        with destination.open("xb") as raw_destination:
            with wave.open(raw_destination, "wb") as output:
                output.setnchannels(decoder.channels)
                output.setsampwidth(_SUPPORTED_SAMPLE_WIDTH_BYTES)
                output.setframerate(decoder.sample_rate_hz)
                while remaining_frames:
                    payload = source.readframes(min(_FRAMES_PER_READ, remaining_frames))
                    if not payload or len(payload) % frame_width:
                        raise TranscriptionError(
                            "Decoded audio ended before the planned segment boundary"
                        )
                    frames_read = len(payload) // frame_width
                    if frames_read > remaining_frames:
                        payload = payload[: remaining_frames * frame_width]
                        frames_read = remaining_frames
                    output.writeframesraw(payload)
                    remaining_frames -= frames_read
