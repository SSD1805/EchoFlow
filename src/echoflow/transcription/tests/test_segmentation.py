import struct
import wave

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.transcription.errors import TranscriptionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    DecodeConfiguration,
    DecodeStrategy,
    SegmentationConfiguration,
)
from echoflow.transcription.segmentation import WaveAudioSegmenter


def decoder(*, sample_rate=10, channels=1):
    return DecodeConfiguration(
        DecodeStrategy.DIRECT,
        "pcm_s16le",
        sample_rate,
        channels,
    )


def write_wave(path, frame_count, *, sample_rate=10, channels=1, sample_width=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        if sample_width == 2 and channels == 1:
            payload = b"".join(
                struct.pack("<h", index % 32_767) for index in range(frame_count)
            )
        else:
            payload = b"\0" * frame_count * channels * sample_width
        output.writeframes(payload)
    return path


@pytest.mark.parametrize(
    ("frame_count", "expected_bounds"),
    [
        (19, ((0, 19),)),
        (20, ((0, 20),)),
        (21, ((0, 20), (20, 21))),
    ],
)
def test_segment_boundary_t_minus_one_t_and_t_plus_one(
    tmp_path, frame_count, expected_bounds
):
    source = write_wave(tmp_path / "source.wav", frame_count)
    windows = WaveAudioSegmenter().plan(
        source,
        decoder(),
        SegmentationConfiguration(segment_duration_seconds=2),
    )
    assert tuple((window.start_frame, window.end_frame) for window in windows) == (
        expected_bounds
    )
    assert tuple(window.index for window in windows) == tuple(range(len(windows)))
    assert tuple(window.segment_id for window in windows) == tuple(
        f"audio-{index:06d}" for index in range(len(windows))
    )


def test_materialized_segment_contains_exact_planned_frames_and_is_cleanable(tmp_path):
    source = write_wave(tmp_path / "source.wav", 25)
    segmenter = WaveAudioSegmenter()
    window = AudioSegmentWindow(1, 20, 25, 10)

    materialized = segmenter.materialize(
        source,
        window,
        decoder(),
        tmp_path / "private-job",
    )

    assert materialized.window == window
    assert materialized.path.name == "audio-000001.wav"
    with wave.open(str(materialized.path), "rb") as result:
        assert result.getframerate() == 10
        assert result.getnchannels() == 1
        assert result.getsampwidth() == 2
        assert result.getnframes() == 5
        assert result.readframes(5) == b"".join(
            struct.pack("<h", index) for index in range(20, 25)
        )

    segmenter.cleanup(materialized)
    assert not materialized.path.exists()


def test_plan_rejects_empty_or_noncanonical_audio(tmp_path):
    empty = write_wave(tmp_path / "empty.wav", 0)
    with pytest.raises(
        TranscriptionError, match="^Decoded audio contains no usable PCM frames$"
    ):
        WaveAudioSegmenter().plan(empty, decoder(), SegmentationConfiguration())

    stereo = write_wave(tmp_path / "stereo.wav", 10, channels=2)
    with pytest.raises(
        TranscriptionError,
        match="^Decoded audio does not match the planned canonical PCM format$",
    ):
        WaveAudioSegmenter().plan(stereo, decoder(), SegmentationConfiguration())


def test_plan_wraps_invalid_wave_without_leaking_native_detail(tmp_path):
    source = tmp_path / "not-wave.wav"
    source.write_bytes(b"private malformed detail")
    with pytest.raises(
        TranscriptionError,
        match="^Decoded audio could not be read as canonical WAV$",
    ) as error:
        WaveAudioSegmenter().plan(source, decoder(), SegmentationConfiguration())
    assert "private malformed detail" not in str(error.value)


def test_materialize_rejects_window_past_source_and_removes_partial_file(tmp_path):
    source = write_wave(tmp_path / "source.wav", 10)
    window = AudioSegmentWindow(0, 0, 11, 10)
    workspace = tmp_path / "private-job"
    with pytest.raises(
        TranscriptionError,
        match="^Audio segment window exceeds decoded audio length$",
    ):
        WaveAudioSegmenter().materialize(source, window, decoder(), workspace)
    assert not (workspace / "segments/audio-000000.wav").exists()


@given(
    frame_count=st.integers(min_value=1, max_value=2_000),
    sample_rate=st.integers(min_value=1, max_value=40),
    duration_seconds=st.integers(min_value=1, max_value=20),
)
def test_segment_plan_is_deterministic_gapless_and_bounded(
    tmp_path, frame_count, sample_rate, duration_seconds
):
    source = write_wave(
        tmp_path / "property.wav", frame_count, sample_rate=sample_rate
    )
    decode = decoder(sample_rate=sample_rate)
    configuration = SegmentationConfiguration(
        segment_duration_seconds=duration_seconds
    )
    segmenter = WaveAudioSegmenter()

    first = segmenter.plan(source, decode, configuration)
    second = segmenter.plan(source, decode, configuration)

    assert first == second
    assert first[0].start_frame == 0
    assert first[-1].end_frame == frame_count
    frames_per_segment = sample_rate * duration_seconds
    for index, window in enumerate(first):
        assert window.index == index
        assert 0 < window.end_frame - window.start_frame <= frames_per_segment
        if index:
            assert first[index - 1].end_frame == window.start_frame
