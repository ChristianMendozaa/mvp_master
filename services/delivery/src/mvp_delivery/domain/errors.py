class DeliveryError(Exception):
    code = "delivery_error"


class InvalidExecutionTransition(DeliveryError):
    code = "invalid_execution_transition"


class BudgetExceeded(DeliveryError):
    code = "budget_exceeded"


class RunnerUnavailable(DeliveryError):
    code = "runner_unavailable"


class InvalidEnrollment(DeliveryError):
    code = "invalid_enrollment"
