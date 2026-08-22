from scholion.core.errors import ErrorCode, ScholionError


class ResourceAdmissionError(ScholionError):
    code = ErrorCode.RESOURCE_ADMISSION
    exit_code = 2


class TranscriptionDependencyError(ScholionError):
    code = ErrorCode.TRANSCRIPTION_DEPENDENCY
    exit_code = 2


class ModelUnavailableError(ScholionError):
    code = ErrorCode.MODEL_UNAVAILABLE
    exit_code = 2


class TranscriptionError(ScholionError):
    code = ErrorCode.TRANSCRIPTION
    exit_code = 2


class AudioEnhancementError(TranscriptionError):
    """Private preprocessing failed or violated the canonical audio contract."""


class CheckpointError(TranscriptionError):
    """Private resumability state is missing, corrupt, or incompatible."""


class DiarizationDependencyError(ScholionError):
    code = ErrorCode.DIARIZATION_DEPENDENCY
    exit_code = 2


class DiarizationModelUnavailableError(ScholionError):
    code = ErrorCode.DIARIZATION_MODEL_UNAVAILABLE
    exit_code = 2


class DiarizationError(ScholionError):
    code = ErrorCode.DIARIZATION
    exit_code = 2
