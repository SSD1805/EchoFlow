import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.transcription.assembly import TranscriptAssembler
from echoflow.transcription.errors import TranscriptionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    EngineTranscript,
    RecognizedSegment,
)


def engine_result(
    *segments,
    language="en",
    probability=0.9,
    version="1.2.1",
):
    return EngineTranscript(tuple(segments), language, probability, version)


def test_assembly_rebases_local_timestamps_and_reindexes_across_windows():
    first = AudioSegmentWindow(0, 0, 10, 10)
    second = AudioSegmentWindow(1, 10, 20, 10)
    result = TranscriptAssembler().assemble(
        [
            (
                first,
                engine_result(
                    RecognizedSegment(0, 0.1, 0.9, "Hello", -0.2, 0.1),
                    language=None,
                    probability=None,
                ),
            ),
            (
                second,
                engine_result(
                    RecognizedSegment(0, 0.0, 0.5, "world.", -0.3, 0.2),
                    language="en",
                    probability=0.98,
                ),
            ),
        ]
    )

    assert tuple(segment.index for segment in result.segments) == (0, 1)
    assert tuple(
        (segment.start_seconds, segment.end_seconds, segment.text)
        for segment in result.segments
    ) == ((0.1, 0.9, "Hello"), (1.0, 1.5, "world."))
    assert result.language == "en"
    assert result.language_probability == 0.98
    assert result.engine_version == "1.2.1"


def test_timestamp_quantization_tolerance_is_clamped_to_window_end():
    window = AudioSegmentWindow(0, 0, 10, 10)
    result = TranscriptAssembler().assemble(
        [
            (
                window,
                engine_result(RecognizedSegment(0, 0.9, 1.04, "boundary")),
            )
        ]
    )
    assert result.segments[0].end_seconds == 1.0


def test_timestamp_beyond_tolerance_is_rejected():
    window = AudioSegmentWindow(0, 0, 10, 10)
    with pytest.raises(
        TranscriptionError,
        match="^The transcription engine returned timestamps outside its audio segment$",
    ):
        TranscriptAssembler().assemble(
            [(window, engine_result(RecognizedSegment(0, 0.9, 1.06, "bad")))]
        )


@pytest.mark.parametrize(
    "windows",
    [
        (AudioSegmentWindow(0, 1, 10, 10),),
        (AudioSegmentWindow(1, 0, 10, 10),),
        (
            AudioSegmentWindow(0, 0, 10, 10),
            AudioSegmentWindow(1, 11, 20, 10),
        ),
        (
            AudioSegmentWindow(0, 0, 10, 10),
            AudioSegmentWindow(1, 10, 20, 20),
        ),
    ],
)
def test_assembly_rejects_noncanonical_window_sequences(windows):
    results = [(window, engine_result()) for window in windows]
    with pytest.raises(TranscriptionError, match="^Audio segment results"):
        TranscriptAssembler().assemble(results)


def test_assembly_rejects_mixed_engine_versions():
    windows = (
        AudioSegmentWindow(0, 0, 10, 10),
        AudioSegmentWindow(1, 10, 20, 10),
    )
    with pytest.raises(
        TranscriptionError,
        match="^Audio segments were transcribed with inconsistent engine versions$",
    ):
        TranscriptAssembler().assemble(
            [
                (windows[0], engine_result(version="1.2.1")),
                (windows[1], engine_result(version="1.2.2")),
            ]
        )


def test_assembly_rejects_noncontiguous_engine_indices():
    window = AudioSegmentWindow(0, 0, 10, 10)
    with pytest.raises(
        TranscriptionError,
        match="^The transcription engine returned noncontiguous segment indices$",
    ):
        TranscriptAssembler().assemble(
            [(window, engine_result(RecognizedSegment(2, 0, 1, "bad index")))]
        )


def test_assembly_requires_at_least_one_audio_window():
    with pytest.raises(
        TranscriptionError,
        match="^No audio segment results were available to assemble$",
    ):
        TranscriptAssembler().assemble([])


@given(
    frame_lengths=st.lists(
        st.integers(min_value=1, max_value=1_000), min_size=1, max_size=20
    )
)
def test_assembly_of_contiguous_full_window_results_preserves_source_timeline(
    frame_lengths,
):
    sample_rate = 100
    windows = []
    results = []
    start = 0
    for index, frame_length in enumerate(frame_lengths):
        end = start + frame_length
        window = AudioSegmentWindow(index, start, end, sample_rate)
        windows.append(window)
        results.append(
            (
                window,
                engine_result(
                    RecognizedSegment(
                        0,
                        0,
                        frame_length / sample_rate,
                        f"part {index}",
                    )
                ),
            )
        )
        start = end

    assembled = TranscriptAssembler().assemble(results)

    assert len(assembled.segments) == len(windows)
    assert tuple(segment.index for segment in assembled.segments) == tuple(
        range(len(windows))
    )
    assert assembled.segments[0].start_seconds == 0
    assert assembled.segments[-1].end_seconds == windows[-1].end_seconds
