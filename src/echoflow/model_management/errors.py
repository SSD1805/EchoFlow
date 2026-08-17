from echoflow.core.errors import EchoFlowError, ErrorCode


class ModelManagementError(EchoFlowError):
    code = ErrorCode.MODEL_UNAVAILABLE
    exit_code = 2
