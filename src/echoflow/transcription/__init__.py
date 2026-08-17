"""Resource-aware local transcription capability."""

from echoflow.transcription.audio import DecodedAudio, FfmpegAudioDecoder
from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.language import LinguaLanguageAttributor
from echoflow.transcription.models import (
    AutoLanguageMode,
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineProvenance,
    EngineTranscript,
    LanguageAttributionProvenance,
    LanguageSpan,
    RecognizedSegment,
    ResourceEstimate,
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.transcription.planner import TranscriptionJobPlanner

__all__ = [
    "AutoLanguageMode",
    "CanonicalTranscript",
    "CpuEngineConfiguration",
    "DecodedAudio",
    "DecodeConfiguration",
    "DecodeStrategy",
    "EngineProvenance",
    "EngineTranscript",
    "FasterWhisperTranscriber",
    "FfmpegAudioDecoder",
    "LanguageAttributionProvenance",
    "LanguageSpan",
    "LinguaLanguageAttributor",
    "RecognizedSegment",
    "ResourceEstimate",
    "TranscriptSource",
    "TranscriptionExecutionResult",
    "TranscriptionExecutor",
    "TranscriptionJobPlan",
    "TranscriptionJobPlanner",
]
