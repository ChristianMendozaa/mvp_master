"""Unit tests for `ClaudeAgentSdkAgent` with the real `claude-agent-sdk` package's
`query()` monkeypatched.

No live credentials or network required (AGENTS.md): `query` never actually spawns
the `claude` binary in these tests. Stub message/block classes are named to match
the real SDK's class names (`SystemMessage`, `AssistantMessage`, `ResultMessage`,
`TextBlock`, `ToolUseBlock`) because the adapter dispatches on `type(...).__name__` —
this keeps tests decoupled from the real dataclasses' exact field set, which may
gain fields across SDK versions.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from uuid import uuid4

import pytest
from mvp_runner.adapters import claude_agent_sdk as claude_agent_sdk_module
from mvp_runner.adapters.claude_agent_sdk import ClaudeAgentSdkAgent
from mvp_runner.adapters.provider_catalog import endpoint_for
from mvp_runner.domain.errors import UnsupportedAuthenticationMode
from mvp_runner.domain.models import AgentRequest


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    name: str


@dataclass
class SystemMessage:
    subtype: str
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class AssistantMessage:
    content: list[object]


@dataclass
class ResultMessage:
    subtype: str
    is_error: bool
    session_id: str
    result: str = ""
    usage: dict[str, object] | None = None


def _request(
    *, workspace: object, authentication_mode: str, provider: str = "anthropic"
) -> AgentRequest:
    return AgentRequest(
        execution_id=uuid4(),
        organization_id=uuid4(),
        provider=provider,
        model="claude-opus-5",
        authentication_mode=authentication_mode,
        secret_reference=None,
        workspace=PurePosixPath(str(workspace)),
        title="Test task",
        problem="Say hi",
        acceptance_criteria=("It says hi",),
        max_turns=2,
        max_duration_seconds=5,
    )


def _fake_query(messages: list[object]):
    async def query(*, prompt: str, options: object) -> AsyncIterator[object]:
        del prompt, options
        for message in messages:
            yield message

    return query


async def test_available_reflects_sdk_installation() -> None:
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("anthropic"))
    assert await agent.available() is True


async def test_local_session_is_never_supported(tmp_path: object) -> None:
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("anthropic"))
    request = _request(workspace=tmp_path, authentication_mode="LOCAL_SESSION")
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_non_anthropic_provider_is_rejected(tmp_path: object) -> None:
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("zhipu-glm"))
    request = _request(
        workspace=tmp_path, authentication_mode="API_KEY_REFERENCE", provider="zhipu-glm"
    )
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_missing_secret_is_rejected(tmp_path: object) -> None:
    agent = ClaudeAgentSdkAgent(secret=None, endpoint=endpoint_for("anthropic"))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_successful_query_maps_events_and_tokens(tmp_path, monkeypatch) -> None:
    messages = [
        SystemMessage(subtype="init", data={"session_id": "sess-1"}),
        AssistantMessage(content=[TextBlock(text="Hi"), ToolUseBlock(name="Bash")]),
        ResultMessage(
            subtype="success",
            is_error=False,
            session_id="sess-1",
            result="Done",
            usage={"input_tokens": 10, "cache_read_input_tokens": 1, "output_tokens": 4},
        ),
    ]
    monkeypatch.setattr(claude_agent_sdk_module, "query", _fake_query(messages))
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("anthropic"))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is True
    assert result.session_id == "sess-1"
    assert result.input_tokens == 10
    assert result.output_tokens == 4
    kinds = [event.name for event in result.events]
    assert "session.initialized" in kinds
    assert "tool_use.Bash" in kinds


async def test_query_raising_is_normalized_to_a_failed_result(tmp_path, monkeypatch) -> None:
    """Regression test: the SDK's own `query()` loop can raise a bare `Exception`
    (verified empirically against claude-agent-sdk 0.2.128) rather than yielding a
    `ResultMessage` with `is_error=True` — this must never crash the job."""

    async def failing_query(*, prompt: str, options: object) -> AsyncIterator[object]:
        del prompt, options
        yield SystemMessage(subtype="init", data={"session_id": "sess-2"})
        raise Exception("Claude Code returned an error result: success")

    monkeypatch.setattr(claude_agent_sdk_module, "query", failing_query)
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("anthropic"))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is False
    assert any(event.name == "runtime.sdk_error" for event in result.events)


async def test_timeout_is_reported_as_a_failed_result(tmp_path, monkeypatch) -> None:
    import asyncio

    async def slow_query(*, prompt: str, options: object) -> AsyncIterator[object]:
        del prompt, options
        await asyncio.sleep(10)
        yield SystemMessage(subtype="init", data={})

    monkeypatch.setattr(claude_agent_sdk_module, "query", slow_query)
    agent = ClaudeAgentSdkAgent(secret="sk-test", endpoint=endpoint_for("anthropic"))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is False
    assert any(event.name == "runtime.timeout" for event in result.events)
