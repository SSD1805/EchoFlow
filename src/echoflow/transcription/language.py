from __future__ import annotations

import math
from importlib import import_module, metadata
from typing import Any

from echoflow.transcription.errors import (
    TranscriptionDependencyError,
    TranscriptionError,
)
from echoflow.transcription.models import (
    LanguageAttributionProvenance,
    LanguageSpan,
)

_MINIMUM_RELATIVE_DISTANCE = 0.1
_TEXT_UNIT_BOUNDARIES = frozenset(".!?;:,\n")


class LinguaLanguageAttributor:
    """Offline text-unit language attribution backed by Lingua.

    Attribution deliberately avoids Lingua's experimental mixed-section splitter.
    EchoFlow classifies deterministic clause/utterance-sized text units and keeps
    ambiguous units unlabeled rather than publishing low-confidence switches.
    """

    def __init__(self) -> None:
        self._detector: Any | None = None
        self._package_version: str | None = None

    @property
    def provenance(self) -> LanguageAttributionProvenance:
        self._dependency()
        package_version = self._package_version
        if package_version is None:
            raise TranscriptionError(
                "Language attribution package version is unavailable"
            )
        return LanguageAttributionProvenance(
            provider="lingua",
            package_version=package_version,
            mode="bounded_text_units_v1",
        )

    def attribute(self, text: str) -> tuple[LanguageSpan, ...]:
        if not text.strip():
            return ()
        detector = self._detector_instance()
        spans: list[LanguageSpan] = []
        try:
            for start, end in self._text_units(text):
                unit = text[start:end]
                language = detector.detect_language_of(unit)
                if language is None:
                    continue
                confidence = float(detector.compute_language_confidence(unit, language))
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError("invalid language confidence")
                spans.append(
                    LanguageSpan(
                        start_char=start,
                        end_char=end,
                        language=self._language_code(language),
                        confidence=confidence,
                    )
                )
        except Exception as exc:
            if isinstance(exc, TranscriptionError):
                raise
            raise TranscriptionError(
                "Local language attribution failed while analyzing transcript text",
                cause=exc,
            ) from exc
        return tuple(spans)

    def _detector_instance(self) -> Any:
        if self._detector is not None:
            return self._detector
        module = self._dependency()
        try:
            self._detector = (
                module.LanguageDetectorBuilder.from_all_languages()
                .with_minimum_relative_distance(_MINIMUM_RELATIVE_DISTANCE)
                .build()
            )
        except Exception as exc:
            raise TranscriptionError(
                "Local language attribution could not be initialized", cause=exc
            ) from exc
        return self._detector

    def _dependency(self) -> Any:
        try:
            module = import_module("lingua")
            if self._package_version is None:
                self._package_version = metadata.version("lingua-language-detector")
            return module
        except (ImportError, metadata.PackageNotFoundError) as exc:
            raise TranscriptionDependencyError(
                "Language attribution support is not installed; install EchoFlow's "
                "transcription extra",
                cause=exc,
            ) from exc

    @staticmethod
    def _text_units(text: str) -> tuple[tuple[int, int], ...]:
        units: list[tuple[int, int]] = []
        start = 0
        for index, character in enumerate(text):
            if character not in _TEXT_UNIT_BOUNDARIES:
                continue
            bounds = LinguaLanguageAttributor._trim_bounds(text, start, index + 1)
            if bounds[0] < bounds[1]:
                units.append(bounds)
            start = index + 1
        bounds = LinguaLanguageAttributor._trim_bounds(text, start, len(text))
        if bounds[0] < bounds[1]:
            units.append(bounds)
        return tuple(units)

    @staticmethod
    def _language_code(language: object) -> str:
        iso_code = getattr(language, "iso_code_639_1", None)
        if callable(iso_code):
            iso_code = iso_code()
        name = getattr(iso_code, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise TranscriptionError(
                "Language attribution returned an unsupported language identifier"
            )
        return name.lower()

    @staticmethod
    def _trim_bounds(text: str, start: int, end: int) -> tuple[int, int]:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return start, end
