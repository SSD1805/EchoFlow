from echoflow.core.errors import EchoFlowError, ErrorCode


class ResourceAdmissionError(EchoFlowError):
    code = ErrorCode.RESOURCE_ADMISSION
    exit_code = 2


class TranscriptionDependencyError(EchoFlowError):
    code = ErrorCode.TRANSCRIPTION_DEPENDENCY
    exit_code = 2


class ModelUnavailableError(EchoFlowError):
    code = ErrorCode.MODEL_UNAVAILABLE
    exit_code = 2


class TranscriptionError(EchoFlowError):
    code = ErrorCode.TRANSCRIPTION
    exit_code = 2


class AudioEnhancementError(TranscriptionError):
    """Private preprocessing failed or violated the canonical audio contract."""


class CheckpointError(TranscriptionError):
    """Private resumability state is missing, corrupt, or incompatible."""


class DiarizationDependencyError(EchoFlowError):
    code = ErrorCode.DIARIZATION_DEPENDENCY
    exit_code = 2


class DiarizationModelUnavailableError(EchoFlowError):
    code = ErrorCode.DIARIZATION_MODEL_UNAVAILABLE
    exit_code = 2


class DiarizationError(EchoFlowError):
    code = ErrorCode.DIARIZATION
    exit_code = 2
