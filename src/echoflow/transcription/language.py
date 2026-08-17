from __future__ import annotations

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


class LinguaLanguageAttributor:
    """Offline mixed-text language attribution backed by Lingua.

    The dependency is loaded lazily so planning and diagnostics remain usable
    without the optional transcription stack installed.
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
            mode="mixed_text_sections",
        )

    def attribute(self, text: str) -> tuple[LanguageSpan, ...]:
        if not text.strip():
            return ()
        detector = self._detector_instance()
        try:
            raw_results = detector.detect_multiple_languages_of(text)
        except Exception as exc:
            raise TranscriptionError(
                "Local language attribution failed while analyzing transcript text",
                cause=exc,
            ) from exc

        spans: list[LanguageSpan] = []
        for raw in raw_results:
            start = int(raw.start_index)
            end = int(raw.end_index)
            start, end = self._trim_bounds(text, start, end)
            if start >= end:
                continue
            spans.append(
                LanguageSpan(
                    start_char=start,
                    end_char=end,
                    language=self._language_code(raw.language),
                    confidence=None,
                )
            )
        if spans:
            return tuple(spans)

        try:
            language = detector.detect_language_of(text)
        except Exception as exc:
            raise TranscriptionError(
                "Local language attribution failed while analyzing transcript text",
                cause=exc,
            ) from exc
        if language is None:
            return ()
        start, end = self._trim_bounds(text, 0, len(text))
        if start >= end:
            return ()
        return (
            LanguageSpan(
                start_char=start,
                end_char=end,
                language=self._language_code(language),
                confidence=None,
            ),
        )

    def _detector_instance(self) -> Any:
        if self._detector is not None:
            return self._detector
        module = self._dependency()
        try:
            builder = module.LanguageDetectorBuilder.from_all_languages()
            if hasattr(builder, "with_low_accuracy_mode"):
                builder = builder.with_low_accuracy_mode()
            self._detector = builder.build()
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
        if start < 0 or end > len(text) or end < start:
            raise TranscriptionError(
                "Language attribution returned invalid transcript character offsets"
            )
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return start, end
