from types import SimpleNamespace

import pytest

import echoflow.transcription.language as language_module
from echoflow.transcription.errors import (
    TranscriptionDependencyError,
    TranscriptionError,
)
from echoflow.transcription.language import LinguaLanguageAttributor


class _Builder:
    low_accuracy = False

    def __init__(self, detector):
        self.detector = detector

    def with_low_accuracy_mode(self):
        self.low_accuracy = True
        return self

    def build(self):
        return self.detector


def _language(code):
    return SimpleNamespace(iso_code_639_1=SimpleNamespace(name=code.upper()))


def test_attributor_preserves_mixed_language_character_spans(monkeypatch):
    english = _language("en")
    french = _language("fr")
    detector = SimpleNamespace(
        detect_multiple_languages_of=lambda _text: (
            SimpleNamespace(start_index=0, end_index=5, language=english),
            SimpleNamespace(start_index=6, end_index=13, language=french),
        )
    )
    builder = _Builder(detector)
    fake_module = SimpleNamespace(
        LanguageDetectorBuilder=SimpleNamespace(
            from_all_languages=lambda: builder,
        )
    )
    monkeypatch.setattr(language_module, "import_module", lambda _name: fake_module)
    monkeypatch.setattr(language_module.metadata, "version", lambda _name: "2.1.0")

    attributor = LinguaLanguageAttributor()
    spans = attributor.attribute("hello bonjour")

    assert builder.low_accuracy is True
    assert tuple((span.start_char, span.end_char, span.language) for span in spans) == (
        (0, 5, "en"),
        (6, 13, "fr"),
    )
    assert attributor.provenance.to_dict() == {
        "provider": "lingua",
        "package_version": "2.1.0",
        "mode": "mixed_text_sections",
    }


def test_attributor_trims_whitespace_but_preserves_text_relative_offsets(monkeypatch):
    english = _language("en")
    detector = SimpleNamespace(
        detect_multiple_languages_of=lambda _text: (
            SimpleNamespace(start_index=0, end_index=7, language=english),
        )
    )
    fake_module = SimpleNamespace(
        LanguageDetectorBuilder=SimpleNamespace(
            from_all_languages=lambda: _Builder(detector),
        )
    )
    monkeypatch.setattr(language_module, "import_module", lambda _name: fake_module)
    monkeypatch.setattr(language_module.metadata, "version", lambda _name: "2.1.0")

    spans = LinguaLanguageAttributor().attribute(" hello ")

    assert len(spans) == 1
    assert spans[0].start_char == 1
    assert spans[0].end_char == 6


def test_attributor_rejects_invalid_library_offsets(monkeypatch):
    detector = SimpleNamespace(
        detect_multiple_languages_of=lambda _text: (
            SimpleNamespace(start_index=-1, end_index=5, language=_language("en")),
        )
    )
    fake_module = SimpleNamespace(
        LanguageDetectorBuilder=SimpleNamespace(
            from_all_languages=lambda: _Builder(detector),
        )
    )
    monkeypatch.setattr(language_module, "import_module", lambda _name: fake_module)
    monkeypatch.setattr(language_module.metadata, "version", lambda _name: "2.1.0")

    with pytest.raises(
        TranscriptionError,
        match="^Language attribution returned invalid transcript character offsets$",
    ):
        LinguaLanguageAttributor().attribute("hello")


def test_attributor_reports_missing_optional_dependency(monkeypatch):
    def missing(_name):
        raise ImportError("missing")

    monkeypatch.setattr(language_module, "import_module", missing)

    with pytest.raises(
        TranscriptionDependencyError,
        match="^Language attribution support is not installed",
    ):
        LinguaLanguageAttributor().attribute("hello")
