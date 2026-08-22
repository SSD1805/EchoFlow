"""Resource-aware local transcription capability."""

from scholion.transcription.alignment import (
    AlignedRecognizedSegment,
    AlignedWord,
    aligned_words,
)
from scholion.transcription.audio import DecodedAudio, FfmpegAudioDecoder
from scholion.transcription.backend import FasterWhisperTranscriber
from scholion.transcription.enhancement import FfmpegAfftdnEnhancer
from scholion.transcription.enhancement_models import (
    EnhancedAudio,
    EnhancementConfiguration,
    EnhancementMode,
    EnhancementProvenance,
)
from scholion.transcription.executor import TranscriptionExecutor
from scholion.transcription.language import LinguaLanguageAttributor
from scholion.transcription.models import (
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
from scholion.transcription.planner import TranscriptionJobPlanner

__all__ = [
    "AlignedRecognizedSegment",
    "AlignedWord",
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
    "aligned_words",
]
