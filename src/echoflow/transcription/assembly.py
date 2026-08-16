import math
from collections.abc import Sequence

from echoflow.transcription.errors import TranscriptionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    EngineTranscript,
    RecognizedSegment,
)

_TIMESTAMP_TOLERANCE_SECONDS = 0.05
_FLOAT_BOUNDARY_TOLERANCE_SECONDS = 1e-9


class TranscriptAssembler:
    """Rebase sequential segment results onto one source-relative timeline."""

    def assemble(
        self,
        results: Sequence[tuple[AudioSegmentWindow, EngineTranscript]],
    ) -> EngineTranscript:
        if not results:
            raise TranscriptionError(
                "No audio segment results were available to assemble"
            )

        self._validate_windows(results)
        engine_version = results[0][1].engine_version
        if any(result.engine_version != engine_version for _, result in results):
            raise TranscriptionError(
                "Audio segments were transcribed with inconsistent engine versions"
            )

        recognized: list[RecognizedSegment] = []
        language: str | None = None
        language_probability: float | None = None
        for window, result in results:
            if language is None and result.language is not None:
                language = result.language
                language_probability = result.language_probability
            self._append_window(recognized, window, result)

        return EngineTranscript(
            segments=tuple(recognized),
            language=language,
            language_probability=language_probability,
            engine_version=engine_version,
        )

    @staticmethod
    def _validate_windows(
        results: Sequence[tuple[AudioSegmentWindow, EngineTranscript]],
    ) -> None:
        previous: AudioSegmentWindow | None = None
        for expected_index, (window, _) in enumerate(results):
            if window.index != expected_index:
                raise TranscriptionError(
                    "Audio segment results are not contiguous and zero-based"
                )
            if previous is None:
                if window.start_frame != 0:
                    raise TranscriptionError(
                        "Audio segment results do not start at the source origin"
                    )
            elif (
                window.start_frame != previous.end_frame
                or window.sample_rate_hz != previous.sample_rate_hz
            ):
                raise TranscriptionError(
                    "Audio segment results do not form one contiguous source timeline"
                )
            previous = window

    @staticmethod
    def _append_window(
        output: list[RecognizedSegment],
        window: AudioSegmentWindow,
        result: EngineTranscript,
    ) -> None:
        indices = tuple(segment.index for segment in result.segments)
        if indices != tuple(range(len(result.segments))):
            raise TranscriptionError(
                "The transcription engine returned noncontiguous segment indices"
            )

        for segment in result.segments:
            if segment.end_seconds > (
                window.duration_seconds + _TIMESTAMP_TOLERANCE_SECONDS
            ):
                raise TranscriptionError(
                    "The transcription engine returned timestamps outside its audio segment"
                )
            start_seconds = min(
                window.end_seconds, window.start_seconds + segment.start_seconds
            )
            if segment.end_seconds > window.duration_seconds or math.isclose(
                segment.end_seconds,
                window.duration_seconds,
                rel_tol=0,
                abs_tol=_FLOAT_BOUNDARY_TOLERANCE_SECONDS,
            ):
                end_seconds = window.end_seconds
            else:
                end_seconds = window.start_seconds + segment.end_seconds
            output.append(
                RecognizedSegment(
                    index=len(output),
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    text=segment.text,
                    average_log_probability=segment.average_log_probability,
                    no_speech_probability=segment.no_speech_probability,
                )
            )
