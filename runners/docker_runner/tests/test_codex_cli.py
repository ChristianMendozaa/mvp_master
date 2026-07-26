"""Unit tests for `CodexCliAgent`, in particular the fix removing the hard
`RuntimeError` that used to fire on `API_KEY_REFERENCE` even though `capabilities()`
advertised it as supported. No live credentials or network required (AGENTS.md).
"""

import json
import stat
import sys
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pytest
from mvp_runner.adapters.codex_cli import CodexCliAgent
from mvp_runner.adapters.provider_catalog import endpoint_for
from mvp_runner.domain.errors import UnsupportedAuthenticationMode
from mvp_runner.domain.models import AgentRequest


def _write_fake_codex(tmp_path: Path, *, transcript: list[dict[str, object]]) -> Path:
    script = tmp_path / "fake-codex.py"
    lines = "\n".join(f"print({json.dumps(json.dumps(line))})" for line in transcript)
    # The real `codex` binary takes `exec --json ... <prompt>` — the fake only needs
    # to ignore its arguments and print the canned transcript.
    script.write_text(f"#!{sys.executable}\n{lines}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _request(*, workspace: Path, authentication_mode: str) -> AgentRequest:
    return AgentRequest(
        execution_id=uuid4(),
        organization_id=uuid4(),
        provider="openai",
        model="gpt-5.1-codex",
        authentication_mode=authentication_mode,
        secret_reference=None,
        workspace=PurePosixPath(str(workspace)),
        title="Test task",
        problem="Say hi",
        acceptance_criteria=("It says hi",),
        max_turns=2,
        max_duration_seconds=5,
    )


_TRANSCRIPT = [
    {"type": "item.started", "item": {"type": "reasoning"}},
    {"type": "item.completed", "item": {"type": "command_execution"}},
    {
        "type": "turn.completed",
        "usage": {"input_tokens": 7, "cached_input_tokens": 1, "output_tokens": 3},
    },
]


async def test_api_key_reference_with_resolved_secret_succeeds(tmp_path: Path) -> None:
    """Regression test: this used to raise `RuntimeError` unconditionally."""
    executable = _write_fake_codex(tmp_path, transcript=_TRANSCRIPT)
    (tmp_path / ".git").mkdir()  # `_changed_paths` shells `git status`; harmless if empty
    agent = CodexCliAgent(
        secret="sk-test", endpoint=endpoint_for("openai"), executable=str(executable)
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = await agent.execute(request)
    assert result.success is True
    assert result.input_tokens == 7
    assert result.output_tokens == 3


async def test_api_key_reference_without_secret_is_rejected(tmp_path: Path) -> None:
    executable = _write_fake_codex(tmp_path, transcript=_TRANSCRIPT)
    agent = CodexCliAgent(secret=None, endpoint=None, executable=str(executable))
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_unknown_authentication_mode_is_rejected(tmp_path: Path) -> None:
    executable = _write_fake_codex(tmp_path, transcript=_TRANSCRIPT)
    agent = CodexCliAgent(executable=str(executable))
    request = _request(workspace=tmp_path, authentication_mode="ENTERPRISE_CONFIGURATION")
    with pytest.raises(UnsupportedAuthenticationMode):
        await agent.execute(request)


async def test_local_session_uses_codex_home_not_a_secret(tmp_path: Path) -> None:
    executable = _write_fake_codex(tmp_path, transcript=_TRANSCRIPT)
    agent = CodexCliAgent(executable=str(executable))
    request = _request(workspace=tmp_path, authentication_mode="LOCAL_SESSION")
    result = await agent.execute(request)
    assert result.success is True


def test_secret_never_appears_in_serialized_result(tmp_path: Path) -> None:
    import asyncio
    from dataclasses import asdict

    executable = _write_fake_codex(tmp_path, transcript=_TRANSCRIPT)
    agent = CodexCliAgent(
        secret="sk-super-secret-value", endpoint=endpoint_for("openai"), executable=str(executable)
    )
    request = _request(workspace=tmp_path, authentication_mode="API_KEY_REFERENCE")
    result = asyncio.run(agent.execute(request))
    assert "sk-super-secret-value" not in json.dumps(asdict(result), default=str)
