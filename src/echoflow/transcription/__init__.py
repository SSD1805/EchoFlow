"""Resource-aware local transcription capability."""

from echoflow.transcription.audio import DecodedAudio, FfmpegAudioDecoder
from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.models import (
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineProvenance,
    EngineTranscript,
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
    "EngineProvenance",
    "EngineTranscript",
    "FasterWhisperTranscriber",
    "FfmpegAudioDecoder",
    "RecognizedSegment",
    "ResourceEstimate",
    "TranscriptSource",
    "TranscriptionExecutionResult",
    "TranscriptionExecutor",
    "TranscriptionJobPlan",
    "TranscriptionJobPlanner",
]
