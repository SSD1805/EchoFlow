from echoflow.core.errors import EchoFlowError, ErrorCode


class MediaToolUnavailableError(EchoFlowError):
    code = ErrorCode.MEDIA_TOOL_UNAVAILABLE
    exit_code = 1


class MediaProbeError(EchoFlowError):
    code = ErrorCode.MEDIA_PROBE
    exit_code = 2


class UnsupportedMediaError(EchoFlowError):
    code = ErrorCode.UNSUPPORTED_MEDIA
    exit_code = 2


class InputChangedError(EchoFlowError):
    code = ErrorCode.INPUT_CHANGED
    exit_code = 2
