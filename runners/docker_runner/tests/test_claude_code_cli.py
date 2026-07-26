"""Unit tests for `ClaudeCodeCliAgent` using a fake `claude` executable.

No live credentials or network required (AGENTS.md). The fake executable is a
small Python script written to `tmp_path` that emits a canned NDJSON transcript
matching the real `claude --output-format stream-json` shapes captured against an
actual installed CLI (system.init / assistant / result messages, including the
verified quirk where a `result` message can carry `"subtype": "success"` while
`"is_error": true`).
"""

import asyncio
import json
import stat
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pytest
from mvp_runner.adapters.claude_code_cli import ClaudeCodeCliAgent
from mvp_runner.adapters.provider_catalog import endpoint_for
from mvp_runner.domain.errors import UnsupportedAuthenticationMode
from mvp_runner.domain.models import AgentRequest


def _write_fake_claude(
    tmp_path: Path, *, transcript: list[dict[str, object]], sleep_seconds: float = 0
) -> Path:
    script = tmp_path / "fake-claude.py"
    lines = "\n".join(f"print({json.dumps(json.dumps(line))})" for line in transcript)
    sleep_stmt = f"import time; time.sleep({sleep_seconds})\n" if sleep_seconds else ""
    script.write_text(
        f"#!{sys.executable}\nimport sys\n{sleep_stmt}{lines}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _request(
    *, workspace: Path, authentication_mode: str, provider: str = "anthropic"
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


_SUCCESS_TRANSCRIPT = [
    {"type": "system", "subtype": "init", "session_id": "sess-1", "model": "claude-opus-5"},
    {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hi there"}]},
    },
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "sess-1",
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 2, "output_tokens": 5},
    },
]

# Verified against a real CLI run: a failure can carry subtype "success" alongside
# is_error true. Success must be derived from is_error, never from subtype alone.
_AUTH_FAILURE_TRANSCRIPT = [
    {"type": "system", "subtype": "init", "session_id": "sess-2", "model": "claude-opus-5"},
    {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Invalid API key · Fix external API key"}]
        },
    },
    {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "session_id": "sess-2",
        "usage": {"input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0},
    },
]


async def test_successful_result_maps_events_and_tokens(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(
        secret="sk-test", endpoint=endpoint_for("anthropic"), executable=str(executable)
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is True
    assert result.session_id == "sess-1"
    assert result.input_tokens == 10
    assert result.cached_input_tokens == 2
    assert result.output_tokens == 5
    assert any(event.name == "result.success" for event in result.events)


async def test_is_error_true_with_subtype_success_is_reported_as_failure(tmp_path: Path) -> None:
    """Regression test for the empirically-found CLI quirk: `subtype` alone is not
    a reliable success signal."""
    executable = _write_fake_claude(tmp_path, transcript=_AUTH_FAILURE_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(
        secret="sk-test", endpoint=endpoint_for("anthropic"), executable=str(executable)
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is False
    error_events = [event for event in result.events if event.kind.value == "ERROR"]
    assert error_events


async def test_local_session_rejects_non_anthropic_provider(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(executable=str(executable))
    request = _request(
        workspace=tmp_path, authentication_mode="LOCAL_SESSION", provider="zhipu-glm"
    )
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_api_key_reference_without_resolved_secret_is_rejected(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(secret=None, endpoint=None, executable=str(executable))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_third_party_provider_sets_base_url_not_api_key(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(
        secret="zhipu-secret", endpoint=endpoint_for("zhipu-glm"), executable=str(executable)
    )
    request = _request(
        workspace=tmp_path, authentication_mode="API_KEY_REFERENCE", provider="zhipu-glm"
    )
    environment = agent._build_environment(request)
    assert environment["ANTHROPIC_BASE_URL"] == "https://open.bigmodel.cn/api/anthropic"
    assert environment["ANTHROPIC_AUTH_TOKEN"] == "zhipu-secret"
    assert "ANTHROPIC_API_KEY" not in environment


async def test_timeout_is_reported_as_a_failed_result_not_an_exception(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT, sleep_seconds=10)
    agent = ClaudeCodeCliAgent(
        secret="sk-test", endpoint=endpoint_for("anthropic"), executable=str(executable)
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is False
    assert any(event.name == "runtime.timeout" for event in result.events)


async def test_cancel_before_execute_raises_cancelled_error(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_SUCCESS_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(
        secret="sk-test", endpoint=endpoint_for("anthropic"), executable=str(executable)
    )
    await agent.cancel()
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    with pytest.raises(asyncio.CancelledError):
        await agent.execute(request)


def test_secret_never_appears_in_serialized_result(tmp_path: Path) -> None:
    executable = _write_fake_claude(tmp_path, transcript=_AUTH_FAILURE_TRANSCRIPT)
    agent = ClaudeCodeCliAgent(
        secret="sk-super-secret-value",
        endpoint=endpoint_for("anthropic"),
        executable=str(executable),
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = asyncio.run(agent.execute(request))
    assert "sk-super-secret-value" not in json.dumps(asdict(result), default=str)
