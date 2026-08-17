from collections.abc import Callable, Iterable
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from echoflow.transcription.errors import (
    ModelUnavailableError,
    TranscriptionDependencyError,
    TranscriptionError,
)
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    EngineTranscript,
    RecognizedSegment,
)

_LANGUAGE_DETECTION_WINDOW_SECONDS = 8


class FasterWhisperSession:
    """One loaded faster-whisper model reused for a single EchoFlow job."""

    def __init__(
        self,
        *,
        model: Any,
        configuration: CpuEngineConfiguration,
        engine_version: str,
    ):
        self.model = model
        self.configuration = configuration
        self.engine_version = engine_version

    def transcribe(self, audio_path: Path) -> EngineTranscript:
        try:
            requested_language = self.configuration.language
            multilingual = requested_language is None
            raw_segments, info = self.model.transcribe(
                str(audio_path),
                beam_size=self.configuration.beam_size,
                language=requested_language,
                word_timestamps=False,
                multilingual=multilingual,
                chunk_length=(
                    _LANGUAGE_DETECTION_WINDOW_SECONDS if multilingual else None
                ),
                condition_on_previous_text=not multilingual,
                vad_filter=False,
                log_progress=False,
            )
            language = FasterWhisperTranscriber._optional_text(
                getattr(info, "language", None)
            )
            language_probability = FasterWhisperTranscriber._optional_float(
                getattr(info, "language_probability", None)
            )
            segments = FasterWhisperTranscriber._segments(
                raw_segments,
                detected_language=None if multilingual else language,
                language_probability=None if multilingual else language_probability,
            )
            return EngineTranscript(
                segments=segments,
                language=language,
                language_probability=language_probability,
                engine_version=self.engine_version,
            )
        except TranscriptionError:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TranscriptionError(
                "The transcription engine failed while processing audio", cause=exc
            ) from exc


class FasterWhisperTranscriber:
    """Open job-scoped faster-whisper sessions from managed local model plans."""

    def __init__(
        self,
        *,
        module_loader: Callable[[str], Any] = import_module,
        version_reader: Callable[[str], str] = metadata.version,
    ):
        self.module_loader = module_loader
        self.version_reader = version_reader

    def open_session(
        self,
        configuration: CpuEngineConfiguration,
    ) -> FasterWhisperSession:
        module, version = self._dependency()
        model = self._model(module, configuration)
        return FasterWhisperSession(
            model=model,
            configuration=configuration,
            engine_version=version,
        )

    def _dependency(self) -> tuple[Any, str]:
        try:
            module = self.module_loader("faster_whisper")
            version = self.version_reader("faster-whisper")
        except (ImportError, metadata.PackageNotFoundError) as exc:
            raise TranscriptionDependencyError(
                "CPU transcription support is not installed; install EchoFlow's "
                "transcription extra",
                cause=exc,
            ) from exc
        return module, version

    @staticmethod
    def _model(module: Any, configuration: CpuEngineConfiguration) -> Any:
        try:
            return module.WhisperModel(
                configuration.model,
                device=configuration.device,
                compute_type=configuration.compute_type,
                cpu_threads=configuration.cpu_threads,
                num_workers=1,
                download_root=str(configuration.model_cache_path),
                local_files_only=True,
                revision=configuration.model_revision,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise ModelUnavailableError(
                f"Managed model '{configuration.model}' is unavailable locally; run "
                f"`echoflow models install {configuration.model}` to reinstall it",
                cause=exc,
            ) from exc

    @classmethod
    def _segments(
        cls,
        raw_segments: Iterable[Any],
        *,
        detected_language: str | None = None,
        language_probability: float | None = None,
    ) -> tuple[RecognizedSegment, ...]:
        recognized: list[RecognizedSegment] = []
        for raw in raw_segments:
            text = str(getattr(raw, "text", "")).strip()
            if not text:
                continue
            try:
                recognized.append(
                    RecognizedSegment(
                        index=len(recognized),
                        start_seconds=float(raw.start),
                        end_seconds=float(raw.end),
                        text=text,
                        average_log_probability=cls._optional_float(
                            getattr(raw, "avg_logprob", None)
                        ),
                        no_speech_probability=cls._optional_float(
                            getattr(raw, "no_speech_prob", None)
                        ),
                        detected_language=detected_language,
                        language_probability=language_probability,
                    )
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise TranscriptionError(
                    "The transcription engine returned invalid segment data", cause=exc
                ) from exc
        return tuple(recognized)

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value))
        except (TypeError, ValueError) as exc:
            raise TranscriptionError(
                "The transcription engine returned invalid probability data", cause=exc
            ) from exc
