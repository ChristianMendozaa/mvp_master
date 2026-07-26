"""`claude` (Claude Code) CLI adapter.

Supports both authentication modes on the same binary:

- `LOCAL_SESSION`: the operator has already run `claude /login` once and mounted the
  resulting OAuth credentials read-only into the job container (see
  `entrypoints/daemon.py` / `Settings.claude_session_path`). This is only valid with
  `provider == "anthropic"` — a subscription session cannot authenticate against a
  third-party endpoint. Intended for `CUSTOMER_HOSTED` runner pools, where the
  customer owns the subscription.
- `API_KEY_REFERENCE`: the daemon has already resolved a `SecretReference` to a
  plaintext value and injected it as an environment variable before this container
  was launched (see `adapters/leased_secret_resolver.py`). This mode also covers
  Anthropic-*compatible* providers (Zhipu GLM, Moonshot Kimi, ...) — the only thing
  that differs per provider is which environment variables `provider_catalog.py`
  says to set (`ANTHROPIC_API_KEY` vs. `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`).
  This adapter never branches on the provider name itself.

This adapter never resolves a secret itself — it only reads environment variables the
host process already populated, and it never receives a `SecretReference`.
"""

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from mvp_runner.adapters.agent_prompt import build_prompt, changed_paths
from mvp_runner.adapters.provider_catalog import ProviderEndpoint, environment_for
from mvp_runner.domain.errors import UnsupportedAuthenticationMode
from mvp_runner.domain.models import (
    AgentCapabilities,
    AgentEvent,
    AgentEventKind,
    AgentRequest,
    AgentResult,
)


class ClaudeCodeCliAgent:
    name = "claude-code-cli"
    is_development_substitute = False

    def __init__(
        self,
        *,
        secret: str | None = None,
        endpoint: ProviderEndpoint | None = None,
        executable: str = "claude",
    ) -> None:
        self._secret = secret
        self._endpoint = endpoint
        self._executable = executable
        self._process: asyncio.subprocess.Process | None = None
        self._events: list[AgentEvent] = []
        self._cancelled = False

    async def available(self) -> bool:
        process = await asyncio.create_subprocess_exec(
            self._executable,
            "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await process.wait() == 0

    async def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_resume=False,
            supports_structured_events=True,
            supports_usage=True,
            supports_approval=False,
            supported_authentication_modes=("LOCAL_SESSION", "API_KEY_REFERENCE"),
        )

    async def execute(self, request: AgentRequest) -> AgentResult:
        if self._cancelled:
            raise asyncio.CancelledError
        environment = self._build_environment(request)
        prompt = build_prompt(request)
        arguments = [
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-turns",
            str(request.max_turns),
            "--model",
            request.model,
            "--permission-mode",
            "acceptEdits",
        ]
        if request.authentication_mode == "API_KEY_REFERENCE":
            # Verified against the installed CLI: `--bare` forces
            # ANTHROPIC_API_KEY-only auth (OAuth/keychain are never read even if
            # present) and skips hooks/LSP/plugin sync/CLAUDE.md auto-discovery —
            # exactly the reduced, deterministic surface we want for a sandboxed,
            # non-interactive run. Never set for LOCAL_SESSION, which relies on the
            # mounted OAuth session instead.
            arguments.append("--bare")
        self._process = await asyncio.create_subprocess_exec(
            self._executable,
            *arguments,
            cwd=str(request.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(), timeout=request.max_duration_seconds
            )
        except TimeoutError:
            await self.cancel()
            self._events = [
                AgentEvent(
                    sequence=1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.timeout",
                    message="Claude Code CLI did not finish within max_duration_seconds.",
                )
            ]
            return AgentResult(
                success=False,
                summary="Claude Code CLI timed out.",
                session_id=None,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                turns=0,
                changed_paths=(),
                events=tuple(self._events),
            )
        session_id, input_tokens, cached_input_tokens, output_tokens, result_success = (
            self._parse_events(stdout)
        )
        if stderr:
            self._events.append(
                AgentEvent(
                    sequence=len(self._events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.stderr",
                    message=stderr.decode(errors="replace")[-2000:],
                )
            )
        success = self._process.returncode == 0 and result_success
        return AgentResult(
            success=success,
            summary="Claude Code CLI completed." if success else "Claude Code CLI failed.",
            session_id=session_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            turns=sum(event.kind is AgentEventKind.RESULT for event in self._events),
            changed_paths=await changed_paths(Path(request.workspace)),
            events=tuple(self._events),
        )

    async def stream(self) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except TimeoutError:
                self._process.kill()

    def _build_environment(self, request: AgentRequest) -> dict[str, str]:
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", "/home/app"),
        }
        for passthrough in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
            if passthrough in os.environ:
                environment[passthrough] = os.environ[passthrough]
        if request.authentication_mode == "LOCAL_SESSION":
            if request.provider != "anthropic":
                raise UnsupportedAuthenticationMode(
                    "LOCAL_SESSION is only valid with provider 'anthropic' — a "
                    "subscription session cannot authenticate a third-party endpoint"
                )
            environment["CLAUDE_CONFIG_DIR"] = self._prepare_local_session(environment["HOME"])
        elif request.authentication_mode == "API_KEY_REFERENCE":
            if self._endpoint is None or self._secret is None:
                raise UnsupportedAuthenticationMode(
                    "API_KEY_REFERENCE requires a resolved secret and provider endpoint"
                )
            environment.update(environment_for(self._endpoint, self._secret))
        else:
            raise UnsupportedAuthenticationMode(
                f"claude-code-cli does not support authentication_mode "
                f"{request.authentication_mode!r}"
            )
        return environment

    @staticmethod
    def _prepare_local_session(home: str) -> str:
        """Copy the read-only mounted OAuth session into the writable HOME.

        The session is mounted read-only at `/run/secrets/claude` by the host (see
        `Settings.claude_session_path` / `docker_agent.py`); `claude` itself needs a
        writable config directory to run in, so we copy rather than point it directly
        at the read-only mount.
        """
        mounted = Path(os.environ.get("CLAUDE_SESSION_MOUNT", "/run/secrets/claude"))
        target = Path(home) / ".claude"
        if mounted.exists() and not target.exists():
            shutil.copytree(mounted, target)
        return str(target)

    def _parse_events(
        self, stdout: bytes
    ) -> tuple[str | None, int | None, int | None, int | None, bool]:
        """Parse `claude --output-format stream-json` NDJSON into normalized events.

        Returns (session_id, input_tokens, cached_input_tokens, output_tokens,
        result_success). `result_success` defaults to True when no terminal `result`
        message was seen (mirrors the previous behavior of trusting the process exit
        code alone) — verify the exact message shapes against the installed CLI.
        """
        events: list[AgentEvent] = []
        session_id: str | None = None
        input_tokens: int | None = None
        cached_input_tokens: int | None = None
        output_tokens: int | None = None
        result_success = True
        for raw_line in stdout.decode(errors="replace").splitlines():
            try:
                document = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            message_type = str(document.get("type", "runtime.event"))
            if message_type == "system" and document.get("subtype") == "init":
                session_id = _str_or_none(document.get("session_id"))
                events.append(
                    _event(len(events) + 1, AgentEventKind.PLAN, "session.initialized", document)
                )
            elif message_type == "assistant":
                events.extend(_events_for_assistant_message(len(events), document))
            elif message_type == "user":
                events.extend(_events_for_tool_result(len(events), document))
            elif message_type == "result":
                session_id = _str_or_none(document.get("session_id")) or session_id
                subtype = str(document.get("subtype", ""))
                # `is_error` is the authoritative success signal — verified against a
                # real CLI run that `subtype` can be "success" while `is_error` is
                # `true` (e.g. an authentication failure still reports
                # `subtype: "success"`). Never key success off `subtype` alone.
                result_success = not bool(document.get("is_error", False))
                usage = document.get("usage")
                if isinstance(usage, dict):
                    input_tokens = _int_or_none(usage.get("input_tokens"))
                    cached_input_tokens = _int_or_none(usage.get("cache_read_input_tokens"))
                    output_tokens = _int_or_none(usage.get("output_tokens"))
                events.append(
                    AgentEvent(
                        sequence=len(events) + 1,
                        kind=(AgentEventKind.RESULT if result_success else AgentEventKind.ERROR),
                        name=f"result.{subtype or 'unknown'}",
                        message="Claude Code CLI reported a final result.",
                        metadata={
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_input_tokens,
                            "output_tokens": output_tokens,
                        },
                    )
                )
                if input_tokens is not None or output_tokens is not None:
                    events.append(
                        AgentEvent(
                            sequence=len(events) + 1,
                            kind=AgentEventKind.USAGE,
                            name="usage.reported",
                            message="Claude Code CLI reported token usage.",
                            metadata={
                                "input_tokens": input_tokens,
                                "cached_input_tokens": cached_input_tokens,
                                "output_tokens": output_tokens,
                            },
                        )
                    )
            else:
                events.append(
                    AgentEvent(
                        sequence=len(events) + 1,
                        kind=AgentEventKind.TOOL,
                        name=message_type,
                        message="Claude Code CLI emitted a structured runtime event.",
                    )
                )
        self._events = events
        return session_id, input_tokens, cached_input_tokens, output_tokens, result_success


def _events_for_assistant_message(
    sequence_start: int, document: dict[str, object]
) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    message = document.get("message")
    blocks: object = message.get("content", []) if isinstance(message, dict) else []
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            events.append(
                AgentEvent(
                    sequence=sequence_start + len(events) + 1,
                    kind=AgentEventKind.PLAN,
                    name="assistant.text",
                    message=str(block.get("text", ""))[:2000],
                )
            )
        elif block_type == "tool_use":
            tool_name = str(block.get("name", "unknown"))
            kind = AgentEventKind.COMMAND if tool_name == "Bash" else AgentEventKind.TOOL
            events.append(
                AgentEvent(
                    sequence=sequence_start + len(events) + 1,
                    kind=kind,
                    name=f"tool_use.{tool_name}",
                    message=f"Claude Code CLI invoked the {tool_name} tool.",
                    metadata={"tool.name": tool_name},
                )
            )
    return events


def _events_for_tool_result(sequence_start: int, document: dict[str, object]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    message = document.get("message")
    blocks: object = message.get("content", []) if isinstance(message, dict) else []
    for block in blocks if isinstance(blocks, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
            events.append(
                AgentEvent(
                    sequence=sequence_start + len(events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="tool_result.error",
                    message=str(block.get("content", ""))[:2000],
                )
            )
    return events


def _event(
    sequence: int, kind: AgentEventKind, name: str, document: dict[str, object]
) -> AgentEvent:
    metadata: dict[str, str | int | bool | None] = {}
    if "model" in document:
        metadata["model"] = _str_or_none(document.get("model"))
    return AgentEvent(
        sequence=sequence,
        kind=kind,
        name=name,
        message="Claude Code CLI session started.",
        metadata=metadata,
    )


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None
