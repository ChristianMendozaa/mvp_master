"""Unit tests for `entrypoints/job.py::_execute` — the actual production
composition root the daemon runs inside the isolated job container (as opposed to
`RunnerExecutionService`, which only the test suite uses).
"""

from pathlib import PurePosixPath
from uuid import uuid4

import pytest
from mvp_runner.domain.models import AgentEventKind, AgentRequest
from mvp_runner.entrypoints.job import _execute


def _request(*, authentication_mode: str, provider: str = "local") -> AgentRequest:
    return AgentRequest(
        execution_id=uuid4(),
        organization_id=uuid4(),
        provider=provider,
        model="deterministic-v1",
        authentication_mode=authentication_mode,
        secret_reference=None,
        workspace=PurePosixPath("/workspace"),
        title="Delivery status",
        problem="The delivery state is unclear.",
        acceptance_criteria=("The status is visible.",),
        max_turns=2,
        max_duration_seconds=30,
    )


async def test_unsupported_authentication_mode_yields_normalized_error_result() -> None:
    request = _request(authentication_mode="API_KEY_REFERENCE")
    result = await _execute(runtime="deterministic", request=request, secret=None)
    assert result.success is False
    assert len(result.events) == 1
    assert result.events[0].kind is AgentEventKind.ERROR
    assert "unsupportedauthenticationmode" in result.events[0].name


async def test_unsupported_runtime_yields_normalized_error_result() -> None:
    request = _request(authentication_mode="NONE")
    result = await _execute(runtime="not-a-real-runtime", request=request, secret=None)
    assert result.success is False
    assert result.events[0].kind is AgentEventKind.ERROR
    assert "unsupportedruntime" in result.events[0].name


async def test_unknown_provider_yields_normalized_error_result() -> None:
    request = _request(authentication_mode="NONE", provider="not-a-real-provider")
    result = await _execute(runtime="deterministic", request=request, secret=None)
    assert result.success is False
    assert "unknownprovider" in result.events[0].name


async def test_supported_combination_reaches_the_real_agent() -> None:
    """A valid (runtime, provider, authentication_mode) combination must pass the
    registry/capability gate and reach the real adapter's `execute()` — proven here
    by getting a `FileNotFoundError` from `DeterministicAgent` (this unit test
    process has no `/workspace`), not a normalized gate-rejection `AgentResult`.
    A gate rejection would instead return cleanly with an `ERROR` event."""
    request = _request(authentication_mode="NONE")
    with pytest.raises(FileNotFoundError):
        await _execute(runtime="deterministic", request=request, secret=None)
