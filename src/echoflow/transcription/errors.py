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
