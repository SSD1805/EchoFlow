from dataclasses import FrozenInstanceError

import pytest

from echoflow.transcription.alignment import (
    AlignedRecognizedSegment,
    AlignedWord,
    aligned_words,
)
from echoflow.transcription.assembly import TranscriptAssembler
from echoflow.transcription.diarization import project_speaker_refs
from echoflow.transcription.models import AudioSegmentWindow, EngineTranscript
from echoflow.transcription.speaker_models import SpeakerTurn


def aligned_segment(
    *,
    index=0,
    start=0.0,
    end=2.0,
    text="hello world",
    words=None,
):
    return AlignedRecognizedSegment(
        index=index,
        start_seconds=start,
        end_seconds=end,
        text=text,
        words=(
            tuple(words)
            if words is not None
            else (
                AlignedWord(start, start + 1.0, "hello", 0.9),
                AlignedWord(start + 1.0, end, "world", 0.8),
            )
        ),
    )


def test_aligned_word_is_frozen_json_safe_and_allows_zero_duration():
    word = AlignedWord(1.25, 1.25, "yes", 0.75)

    assert word.to_dict() == {
        "start_seconds": 1.25,
        "end_seconds": 1.25,
        "text": "yes",
        "probability": 0.75,
        "speaker_ref": None,
    }
    assert not hasattr(word, "__dict__")
    with pytest.raises(FrozenInstanceError):
        word.text = "changed"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((-0.1, 0.1, "word"), "word timestamps must be finite and ordered"),
        ((1.0, 0.5, "word"), "word timestamps must be finite and ordered"),
        ((float("nan"), 1.0, "word"), "word timestamps must be finite and ordered"),
        ((0.0, 1.0, " "), "word text cannot be empty"),
        ((0.0, 1.0, "word", -0.1), "word probability must be between 0 and 1"),
        ((0.0, 1.0, "word", 1.1), "word probability must be between 0 and 1"),
    ],
)
def test_aligned_word_rejects_invalid_evidence(args, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        AlignedWord(*args)


def test_aligned_segment_serializes_words_without_changing_base_segment_contract():
    segment = aligned_segment()

    document = segment.to_dict()
    assert document["segment_id"] == "segment-000000"
    assert [word["text"] for word in document["words"]] == ["hello", "world"]
    assert aligned_words(segment) == segment.words


@pytest.mark.parametrize(
    ("words", "message"),
    [
        ((AlignedWord(0.0, 1.1, "late"),), "word timestamp ends after its segment"),
        (
            (AlignedWord(0.0, 0.7, "one"), AlignedWord(0.6, 1.0, "two")),
            "word timestamps must be ordered and non-overlapping",
        ),
    ],
)
def test_aligned_segment_rejects_words_outside_or_crossing_each_other(words, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        aligned_segment(end=1.0, text="one two", words=words)


def test_assembler_rebases_aligned_words_to_source_relative_timeline():
    first_window = AudioSegmentWindow(0, 0, 100, 10)
    second_window = AudioSegmentWindow(1, 100, 200, 10)
    first = EngineTranscript(
        (aligned_segment(start=1.0, end=3.0),),
        "en",
        0.9,
        "1.2.1",
    )
    second = EngineTranscript(
        (aligned_segment(start=2.0, end=4.0),),
        "en",
        0.8,
        "1.2.1",
    )

    result = TranscriptAssembler().assemble(
        ((first_window, first), (second_window, second))
    )

    assert [(segment.start_seconds, segment.end_seconds) for segment in result.segments] == [
        (1.0, 3.0),
        (12.0, 14.0),
    ]
    assert [
        (word.start_seconds, word.end_seconds)
        for word in aligned_words(result.segments[1])
    ] == [(12.0, 13.0), (13.0, 14.0)]


def test_word_alignment_makes_speaker_handoff_visible_without_false_segment_precision():
    segment = aligned_segment(
        start=0.0,
        end=4.0,
        text="one two three four",
        words=(
            AlignedWord(0.0, 1.0, "one"),
            AlignedWord(1.0, 2.0, "two"),
            AlignedWord(2.0, 3.0, "three"),
            AlignedWord(3.0, 4.0, "four"),
        ),
    )
    turns = (
        SpeakerTurn(0.0, 2.0, "speaker-01"),
        SpeakerTurn(2.0, 4.0, "speaker-02"),
    )

    projected = project_speaker_refs((segment,), turns)[0]

    assert projected.speaker_ref is None
    assert [word.speaker_ref for word in aligned_words(projected)] == [
        "speaker-01",
        "speaker-01",
        "speaker-02",
        "speaker-02",
    ]


def test_word_crossing_overlapping_speakers_stays_unattributed():
    segment = aligned_segment(
        start=0.0,
        end=2.0,
        text="hello there",
        words=(
            AlignedWord(0.0, 1.0, "hello"),
            AlignedWord(1.0, 2.0, "there"),
        ),
    )
    turns = (
        SpeakerTurn(0.0, 1.5, "speaker-01"),
        SpeakerTurn(1.5, 2.0, "speaker-02"),
    )

    projected = project_speaker_refs((segment,), turns)[0]

    assert projected.speaker_ref is None
    assert [word.speaker_ref for word in aligned_words(projected)] == [
        "speaker-01",
        None,
    ]


def test_uniform_word_speaker_projection_retains_segment_level_convenience_label():
    segment = aligned_segment()
    turns = (SpeakerTurn(0.0, 2.0, "speaker-01"),)

    projected = project_speaker_refs((segment,), turns)[0]

    assert projected.speaker_ref == "speaker-01"
    assert {word.speaker_ref for word in aligned_words(projected)} == {"speaker-01"}
