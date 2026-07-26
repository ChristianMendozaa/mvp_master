class RunnerError(Exception):
    """Base class for runner domain errors.

    Never include a secret value in the message — only identifiers (runtime name,
    provider name, capability id). `entrypoints/daemon.py`'s `failed_job_result`
    reports only `type(error).__name__` to delivery, but these messages still reach
    runner-local logs, so they must stay safe on their own.
    """


class UnknownProvider(RunnerError):
    """A job referenced a `provider` value with no catalog entry."""


class UnsupportedRuntime(RunnerError):
    """A job requested a `runtime` value with no registered `AgentRuntime`."""


class UnsupportedAuthenticationMode(RunnerError):
    """A job's authentication_mode is not in the selected runtime's capabilities."""


class SecretResolutionFailed(RunnerError):
    """The host-side model-credential lease could not be completed for this job."""
