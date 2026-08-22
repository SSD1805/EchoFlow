from scholion.core.errors import ErrorCode, ScholionError


class MediaToolUnavailableError(ScholionError):
    code = ErrorCode.MEDIA_TOOL_UNAVAILABLE
    exit_code = 1


class MediaProbeError(ScholionError):
    code = ErrorCode.MEDIA_PROBE
    exit_code = 2


class UnsupportedMediaError(ScholionError):
    code = ErrorCode.UNSUPPORTED_MEDIA
    exit_code = 2


class InputChangedError(ScholionError):
    code = ErrorCode.INPUT_CHANGED
    exit_code = 2


class AudioDecodeError(ScholionError):
    code = ErrorCode.AUDIO_DECODE
    exit_code = 2
