"""Claude Agent SDK (Python `claude-agent-sdk` package) adapter.

`API_KEY_REFERENCE` only — Anthropic's terms do not allow a third-party product to
offer claude.ai subscription login through the Agent SDK, so `LOCAL_SESSION` is
refused loudly rather than silently downgraded to API-key mode or routed to the
`claude-code-cli` runtime. The SDK bundles the same underlying `claude` binary as
`claude-code-cli`, but the two are separate `AgentRuntime` adapters because they
have distinct capability surfaces (auth modes) and distinct event parsing.

This adapter never resolves a secret itself. The daemon already resolved it and
this constructor receives the plaintext value directly. It is passed to the SDK via
`ClaudeAgentOptions(env={"ANTHROPIC_API_KEY": ...})` — the SDK spawns the `claude`
binary as a subprocess and merges `options.env` over its own inherited
`os.environ` when building that subprocess's environment (verified against
`claude_agent_sdk` 0.2.128's `_internal/transport/subprocess_cli.py`), so this never
touches the calling Python process's own `os.environ`.

Field names below (`ClaudeAgentOptions.cwd/model/max_turns/permission_mode/
setting_sources/env`, `SystemMessage.subtype/data`, `ResultMessage.session_id/usage/
is_error/subtype`) were verified against a live install of `claude-agent-sdk`
0.2.128 — re-check them if the pinned version in `pyproject.toml` moves.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from mvp_runner.adapters.agent_prompt import build_prompt, changed_paths
from mvp_runner.adapters.provider_catalog import ProviderEndpoint
from mvp_runner.domain.errors import UnsupportedAuthenticationMode
from mvp_runner.domain.models import (
    AgentCapabilities,
    AgentEvent,
    AgentEventKind,
    AgentRequest,
    AgentResult,
)

try:
    from claude_agent_sdk import ClaudeAgentOptions, query

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the SDK is not installed
    _SDK_AVAILABLE = False


class ClaudeAgentSdkAgent:
    name = "claude-agent-sdk"
    is_development_substitute = False

    def __init__(
        self,
        *,
        secret: str | None = None,
        endpoint: ProviderEndpoint | None = None,
    ) -> None:
        self._secret = secret
        self._endpoint = endpoint
        self._events: list[AgentEvent] = []
        self._task: asyncio.Task[None] | None = None
        self._cancelled = False

    async def available(self) -> bool:
        return _SDK_AVAILABLE

    async def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_resume=False,
            supports_structured_events=True,
            supports_usage=True,
            supports_approval=False,
            supported_authentication_modes=("API_KEY_REFERENCE",),
        )

    async def execute(self, request: AgentRequest) -> AgentResult:
        if self._cancelled:
            raise asyncio.CancelledError
        if not _SDK_AVAILABLE:
            raise RuntimeError("claude-agent-sdk is not installed in this job image")
        if request.authentication_mode != "API_KEY_REFERENCE":
            raise UnsupportedAuthenticationMode(
                "claude-agent-sdk only supports API_KEY_REFERENCE — Anthropic's terms "
                "do not permit third-party subscription login through the Agent SDK"
            )
        if request.provider != "anthropic":
            raise UnsupportedAuthenticationMode(
                "claude-agent-sdk only supports the first-party 'anthropic' provider "
                "in this increment"
            )
        if self._secret is None:
            raise UnsupportedAuthenticationMode("API_KEY_REFERENCE requires a resolved secret")
        session_id: str | None = None
        input_tokens: int | None = None
        cached_input_tokens: int | None = None
        output_tokens: int | None = None
        success = False
        summary = "Claude Agent SDK produced no result message."
        events: list[AgentEvent] = []
        try:
            self._task = asyncio.current_task()
            options = ClaudeAgentOptions(
                cwd=str(request.workspace),
                model=request.model,
                max_turns=request.max_turns,
                permission_mode="acceptEdits",
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                setting_sources=[],  # never load the host's ~/.claude/ into the sandbox
                env={"ANTHROPIC_API_KEY": self._secret},
            )
            async with asyncio.timeout(request.max_duration_seconds):
                async for message in query(prompt=build_prompt(request), options=options):
                    kind = type(message).__name__
                    if kind == "SystemMessage" and getattr(message, "subtype", None) == "init":
                        data = getattr(message, "data", {}) or {}
                        session_id = data.get("session_id")
                        events.append(
                            AgentEvent(
                                sequence=len(events) + 1,
                                kind=AgentEventKind.PLAN,
                                name="session.initialized",
                                message="Claude Agent SDK session started.",
                            )
                        )
                    elif kind == "AssistantMessage":
                        events.extend(_events_for_assistant_message(len(events), message))
                    elif kind == "ResultMessage":
                        is_error = bool(getattr(message, "is_error", False))
                        success = not is_error
                        summary = str(getattr(message, "result", "") or "")
                        session_id = getattr(message, "session_id", session_id)
                        usage = getattr(message, "usage", None)
                        if isinstance(usage, dict):
                            input_tokens = _int_or_none(usage.get("input_tokens"))
                            cached_input_tokens = _int_or_none(usage.get("cache_read_input_tokens"))
                            output_tokens = _int_or_none(usage.get("output_tokens"))
                        events.append(
                            AgentEvent(
                                sequence=len(events) + 1,
                                kind=(AgentEventKind.RESULT if success else AgentEventKind.ERROR),
                                name=f"result.{getattr(message, 'subtype', 'unknown')}",
                                message="Claude Agent SDK reported a final result.",
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
                                    message="Claude Agent SDK reported token usage.",
                                    metadata={
                                        "input_tokens": input_tokens,
                                        "cached_input_tokens": cached_input_tokens,
                                        "output_tokens": output_tokens,
                                    },
                                )
                            )
        except TimeoutError:
            events.append(
                AgentEvent(
                    sequence=len(events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.timeout",
                    message="Claude Agent SDK did not finish within max_duration_seconds.",
                )
            )
            success = False
            summary = "Claude Agent SDK timed out."
        except asyncio.CancelledError:
            events.append(
                AgentEvent(
                    sequence=len(events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.cancelled",
                    message="Claude Agent SDK execution was cancelled.",
                )
            )
            success = False
            summary = "Claude Agent SDK was cancelled."
        except Exception as error:
            # Verified empirically: the SDK's own query loop can raise a bare
            # `Exception` (not a `ResultMessage` with `is_error=True`) for some
            # failures the underlying CLI reports — e.g. an authentication failure
            # surfaces from the CLI as `{"is_error": true, "subtype": "success", ...}`
            # (see the matching comment in `claude_code_cli.py`), and the SDK's
            # `_internal/query.py::receive_messages` turns that combination into a
            # raised `Exception` rather than yielding the result message. Normalize
            # any such failure into a failed `AgentResult` instead of propagating —
            # a raised exception here would otherwise crash the job container.
            events.append(
                AgentEvent(
                    sequence=len(events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.sdk_error",
                    message=str(error)[:2000],
                )
            )
            success = False
            summary = f"Claude Agent SDK reported an error: {error}"[:4000]
        finally:
            self._task = None
        self._events = events
        default_summary = "Claude Agent SDK completed." if success else "Claude Agent SDK failed."
        return AgentResult(
            success=success,
            summary=summary or default_summary,
            session_id=session_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            turns=sum(event.kind is AgentEventKind.RESULT for event in events),
            changed_paths=await changed_paths(Path(request.workspace)),
            events=tuple(events),
        )

    async def stream(self) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event

    async def cancel(self) -> None:
        self._cancelled = True
        if self._task is not None:
            self._task.cancel()


def _events_for_assistant_message(sequence_start: int, message: object) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for block in getattr(message, "content", []) or []:
        block_kind = type(block).__name__
        if block_kind == "TextBlock":
            events.append(
                AgentEvent(
                    sequence=sequence_start + len(events) + 1,
                    kind=AgentEventKind.PLAN,
                    name="assistant.text",
                    message=str(getattr(block, "text", ""))[:2000],
                )
            )
        elif block_kind == "ToolUseBlock":
            tool_name = str(getattr(block, "name", "unknown"))
            kind = AgentEventKind.COMMAND if tool_name == "Bash" else AgentEventKind.TOOL
            events.append(
                AgentEvent(
                    sequence=sequence_start + len(events) + 1,
                    kind=kind,
                    name=f"tool_use.{tool_name}",
                    message=f"Claude Agent SDK invoked the {tool_name} tool.",
                    metadata={"tool.name": tool_name},
                )
            )
    return events


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None
