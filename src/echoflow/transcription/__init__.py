"""Resource-aware local transcription capability."""

from echoflow.transcription.audio import DecodedAudio, FfmpegAudioDecoder
from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.enhancement import FfmpegAfftdnEnhancer
from echoflow.transcription.enhancement_models import (
    EnhancedAudio,
    EnhancementConfiguration,
    EnhancementMode,
    EnhancementProvenance,
)
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.language import LinguaLanguageAttributor
from echoflow.transcription.models import (
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
    "CanonicalTranscript",
    "CpuEngineConfiguration",
    "DecodedAudio",
    "DecodeConfiguration",
    "DecodeStrategy",
    "EnhancedAudio",
    "EnhancementConfiguration",
    "EnhancementMode",
    "EnhancementProvenance",
    "EngineProvenance",
    "EngineTranscript",
    "FasterWhisperTranscriber",
    "FfmpegAfftdnEnhancer",
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
