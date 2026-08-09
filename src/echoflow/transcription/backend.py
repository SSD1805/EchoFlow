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


class FasterWhisperTranscriber:
    """Load one CPU model per job and return engine-neutral segment values."""

    def __init__(
        self,
        *,
        module_loader: Callable[[str], Any] = import_module,
        version_reader: Callable[[str], str] = metadata.version,
    ):
        self.module_loader = module_loader
        self.version_reader = version_reader

    def transcribe(
        self,
        audio_path: Path,
        configuration: CpuEngineConfiguration,
        *,
        allow_model_download: bool,
    ) -> EngineTranscript:
        module, version = self._dependency()
        model = self._model(module, configuration, allow_model_download)
        try:
            raw_segments, info = model.transcribe(
                str(audio_path),
                beam_size=configuration.beam_size,
                language=configuration.language,
                word_timestamps=False,
                vad_filter=False,
                log_progress=False,
            )
            segments = self._segments(raw_segments)
            language = self._optional_text(getattr(info, "language", None))
            language_probability = self._optional_float(
                getattr(info, "language_probability", None)
            )
            return EngineTranscript(
                segments=segments,
                language=language,
                language_probability=language_probability,
                engine_version=version,
            )
        except TranscriptionError:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TranscriptionError(
                "The transcription engine failed while processing audio", cause=exc
            ) from exc

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
    def _model(
        module: Any,
        configuration: CpuEngineConfiguration,
        allow_model_download: bool,
    ) -> Any:
        try:
            return module.WhisperModel(
                configuration.model,
                device=configuration.device,
                compute_type=configuration.compute_type,
                cpu_threads=configuration.cpu_threads,
                num_workers=1,
                download_root=str(configuration.model_cache_path),
                local_files_only=not allow_model_download,
                revision=configuration.model_revision,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            if not allow_model_download:
                raise ModelUnavailableError(
                    "The selected model is not available locally; rerun with "
                    "--allow-model-download to authorize network access",
                    cause=exc,
                ) from exc
            raise TranscriptionError(
                "The selected model could not be downloaded or initialized", cause=exc
            ) from exc

    @classmethod
    def _segments(cls, raw_segments: Iterable[Any]) -> tuple[RecognizedSegment, ...]:
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
