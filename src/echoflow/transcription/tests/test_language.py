from types import SimpleNamespace

import pytest

import echoflow.transcription.language as language_module
from echoflow.transcription.errors import (
    TranscriptionDependencyError,
    TranscriptionError,
)
from echoflow.transcription.language import LinguaLanguageAttributor


class _Detector:
    def __init__(self, languages, confidences):
        self.languages = languages
        self.confidences = confidences
        self.calls = []

    def detect_language_of(self, text):
        self.calls.append(("detect", text))
        return self.languages.get(text)

    def compute_language_confidence(self, text, language):
        self.calls.append(("confidence", text, language))
        return self.confidences[text]


class _Builder:
    def __init__(self, detector):
        self.detector = detector
        self.minimum_relative_distance = None

    def with_minimum_relative_distance(self, distance):
        self.minimum_relative_distance = distance
        return self

    def build(self):
        return self.detector


def _language(code):
    return SimpleNamespace(iso_code_639_1=SimpleNamespace(name=code.upper()))


def _install_fake_lingua(monkeypatch, detector):
    builder = _Builder(detector)
    fake_module = SimpleNamespace(
        LanguageDetectorBuilder=SimpleNamespace(
            from_all_languages=lambda: builder,
        )
    )
    monkeypatch.setattr(language_module, "import_module", lambda _name: fake_module)
    monkeypatch.setattr(language_module.metadata, "version", lambda _name: "2.2.0")
    return builder


def test_attributor_preserves_confident_language_units_and_offsets(monkeypatch):
    english = _language("en")
    french = _language("fr")
    detector = _Detector(
        {
            "hello there.": english,
            "bonjour monde!": french,
        },
        {
            "hello there.": 0.91,
            "bonjour monde!": 0.88,
        },
    )
    builder = _install_fake_lingua(monkeypatch, detector)

    attributor = LinguaLanguageAttributor()
    spans = attributor.attribute("hello there. bonjour monde!")

    assert builder.minimum_relative_distance == 0.1
    assert tuple(
        (span.start_char, span.end_char, span.language, span.confidence)
        for span in spans
    ) == (
        (0, 12, "en", 0.91),
        (13, 27, "fr", 0.88),
    )
    assert attributor.provenance.to_dict() == {
        "provider": "lingua",
        "package_version": "2.2.0",
        "mode": "bounded_text_units_v1",
    }


def test_attributor_leaves_ambiguous_units_unlabeled(monkeypatch):
    english = _language("en")
    detector = _Detector(
        {"hello there.": english, "maybe?": None},
        {"hello there.": 0.82},
    )
    _install_fake_lingua(monkeypatch, detector)

    spans = LinguaLanguageAttributor().attribute("hello there. maybe?")

    assert tuple((span.language, span.start_char, span.end_char) for span in spans) == (
        ("en", 0, 12),
    )
    assert ("confidence", "maybe?", None) not in detector.calls


def test_attributor_uses_clause_and_utterance_boundaries(monkeypatch):
    english = _language("en")
    french = _language("fr")
    detector = _Detector(
        {"hello,": english, "bonjour": french, "merci": french},
        {"hello,": 0.8, "bonjour": 0.9, "merci": 0.95},
    )
    _install_fake_lingua(monkeypatch, detector)

    spans = LinguaLanguageAttributor().attribute(" hello, bonjour\n merci ")

    assert tuple((span.start_char, span.end_char, span.language) for span in spans) == (
        (1, 7, "en"),
        (8, 15, "fr"),
        (17, 22, "fr"),
    )


def test_attributor_rejects_invalid_library_confidence(monkeypatch):
    english = _language("en")
    detector = _Detector({"hello": english}, {"hello": 2.0})
    _install_fake_lingua(monkeypatch, detector)

    with pytest.raises(
        TranscriptionError,
        match="^Local language attribution failed while analyzing transcript text$",
    ):
        LinguaLanguageAttributor().attribute("hello")


def test_attributor_wraps_detector_failure(monkeypatch):
    class Detector:
        def detect_language_of(self, _text):
            raise RuntimeError("private detector detail")

    _install_fake_lingua(monkeypatch, Detector())

    with pytest.raises(
        TranscriptionError,
        match="^Local language attribution failed while analyzing transcript text$",
    ) as error:
        LinguaLanguageAttributor().attribute("hello")
    assert "private detector detail" not in str(error.value)


def test_attributor_reports_missing_optional_dependency(monkeypatch):
    def missing(_name):
        raise ImportError("missing")

    monkeypatch.setattr(language_module, "import_module", missing)

    with pytest.raises(
        TranscriptionDependencyError,
        match="^Language attribution support is not installed",
    ):
        LinguaLanguageAttributor().attribute("hello")
