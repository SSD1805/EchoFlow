from scholion.core.errors import ScholionError, ErrorCode


class ModelManagementError(ScholionError):
    code = ErrorCode.MODEL_UNAVAILABLE
    exit_code = 2
