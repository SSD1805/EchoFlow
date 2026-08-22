from scholion.core.errors import ErrorCode, ScholionError


class ModelManagementError(ScholionError):
    code = ErrorCode.MODEL_UNAVAILABLE
    exit_code = 2
