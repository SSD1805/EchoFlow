from echoflow.transcription.assembly import TranscriptAssembler
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.models import (
    AudioSegmentWindow,
    LanguageAttributionProvenance,
    LanguageSpan,
    RecognizedSegment,
    EngineTranscript,
)


def test_assembly_preserves_language_changes_on_source_relative_segments():
    windows = (
        AudioSegmentWindow(0, 0, 10, 10),
        AudioSegmentWindow(1, 10, 20, 10),
    )
    results = [
        (
            windows[0],
            EngineTranscript(
                (RecognizedSegment(0, 0, 0.8, "Good morning"),),
                "en",
                0.99,
                "1.2.1",
            ),
        ),
        (
            windows[1],
            EngineTranscript(
                (RecognizedSegment(0, 0, 0.8, "Bonjour Montréal"),),
                "fr",
                0.98,
                "1.2.1",
            ),
        ),
    ]

    assembled = TranscriptAssembler().assemble(results)

    assert assembled.language is None
    assert assembled.language_probability is None
    assert tuple(segment.detected_language for segment in assembled.segments) == (
        "en",
        "fr",
    )
    assert tuple(segment.start_seconds for segment in assembled.segments) == (0.0, 1.0)


def test_language_attribution_preserves_mixed_text_spans_without_false_uniform_label():
    class Attributor:
        @property
        def provenance(self):
            return LanguageAttributionProvenance("test-lid", "1", "mixed")

        def attribute(self, _text):
            return (
                LanguageSpan(0, 5, "en"),
                LanguageSpan(6, 13, "fr"),
            )

    executor = object.__new__(TranscriptionExecutor)
    executor.language_attributor = Attributor()
    original = (RecognizedSegment(0, 0, 1, "hello bonjour"),)

    attributed, provenance = executor._attribute_languages(original)

    assert provenance is not None
    assert provenance.provider == "test-lid"
    assert attributed[0].language is None
    assert tuple(span.language for span in attributed[0].language_spans) == ("en", "fr")
    assert attributed[0].text == original[0].text
    assert attributed[0].start_seconds == original[0].start_seconds


def test_language_attribution_sets_uniform_segment_language_when_spans_agree():
    class Attributor:
        @property
        def provenance(self):
            return LanguageAttributionProvenance("test-lid", "1", "uniform")

        def attribute(self, text):
            return (LanguageSpan(0, len(text), "fr"),)

    executor = object.__new__(TranscriptionExecutor)
    executor.language_attributor = Attributor()

    attributed, _ = executor._attribute_languages(
        (RecognizedSegment(0, 0, 1, "bonjour"),)
    )

    assert attributed[0].language == "fr"
