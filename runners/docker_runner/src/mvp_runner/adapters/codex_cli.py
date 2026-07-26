import asyncio
import json
import os
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

# Best-effort mapping from `codex exec --json` event `type` strings to our normalized
# AgentEventKind. Codex's NDJSON shape is not a versioned wire contract we control, so
# any type not listed here degrades to TOOL rather than raising — verify this table
# against the installed `codex` binary's actual output when packaging it (Phase 5/6).
_KIND_BY_EVENT_TYPE: dict[str, AgentEventKind] = {
    "item.started": AgentEventKind.PLAN,
    "item.updated": AgentEventKind.PLAN,
    "item.completed": AgentEventKind.TOOL,
    "turn.completed": AgentEventKind.USAGE,
    "turn.failed": AgentEventKind.ERROR,
    "error": AgentEventKind.ERROR,
}


class CodexCliAgent:
    name = "codex-cli"
    is_development_substitute = False

    def __init__(
        self,
        *,
        secret: str | None = None,
        endpoint: ProviderEndpoint | None = None,
        executable: str = "codex",
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
            supports_resume=True,
            supports_structured_events=True,
            supports_usage=True,
            supports_approval=True,
            supported_authentication_modes=("LOCAL_SESSION", "API_KEY_REFERENCE"),
        )

    async def execute(self, request: AgentRequest) -> AgentResult:
        if self._cancelled:
            raise asyncio.CancelledError
        environment = self._build_environment(request)
        prompt = build_prompt(request)
        self._process = await asyncio.create_subprocess_exec(
            self._executable,
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--model",
            request.model,
            "--cd",
            str(request.workspace),
            prompt,
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
                    message="Codex CLI did not finish within max_duration_seconds.",
                )
            ]
            return AgentResult(
                success=False,
                summary="Codex CLI timed out.",
                session_id=None,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                turns=0,
                changed_paths=(),
                events=tuple(self._events),
            )
        input_tokens, cached_input_tokens, output_tokens = self._parse_events(stdout)
        if stderr:
            self._events.append(
                AgentEvent(
                    sequence=len(self._events) + 1,
                    kind=AgentEventKind.ERROR,
                    name="runtime.stderr",
                    message=stderr.decode(errors="replace")[-2000:],
                )
            )
        success = self._process.returncode == 0
        return AgentResult(
            success=success,
            summary="Codex CLI completed." if success else "Codex CLI failed.",
            session_id=None,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            turns=sum(event.kind is AgentEventKind.USAGE for event in self._events),
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
            "HOME": os.environ.get("HOME", "/nonexistent"),
        }
        for passthrough in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
            if passthrough in os.environ:
                environment[passthrough] = os.environ[passthrough]
        if request.authentication_mode == "LOCAL_SESSION":
            environment["CODEX_HOME"] = os.environ.get("CODEX_HOME", "/home/app/.codex")
        elif request.authentication_mode == "API_KEY_REFERENCE":
            if self._endpoint is None or self._secret is None:
                raise UnsupportedAuthenticationMode(
                    "API_KEY_REFERENCE requires a resolved secret and provider endpoint"
                )
            environment.update(environment_for(self._endpoint, self._secret))
        else:
            raise UnsupportedAuthenticationMode(
                f"codex-cli does not support authentication_mode {request.authentication_mode!r}"
            )
        return environment

    def _parse_events(self, stdout: bytes) -> tuple[int | None, int | None, int | None]:
        """Parse Codex's NDJSON stdout into normalized events, store them on
        `self._events`, and return the last-seen (input, cached_input, output)
        token counts, if any `turn.completed` line carried a `usage` block."""
        events: list[AgentEvent] = []
        input_tokens: int | None = None
        cached_input_tokens: int | None = None
        output_tokens: int | None = None
        for raw_line in stdout.decode(errors="replace").splitlines():
            try:
                document = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            event_type = str(document.get("type", "runtime.event"))
            kind = _KIND_BY_EVENT_TYPE.get(event_type, AgentEventKind.TOOL)
            metadata: dict[str, str | int | bool | None] = {}
            usage = document.get("usage")
            if isinstance(usage, dict):
                input_tokens = _int_or_none(usage.get("input_tokens"))
                cached_input_tokens = _int_or_none(usage.get("cached_input_tokens"))
                output_tokens = _int_or_none(usage.get("output_tokens"))
                metadata = {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                }
            events.append(
                AgentEvent(
                    sequence=len(events) + 1,
                    kind=kind,
                    name=event_type,
                    message="Codex emitted a structured runtime event.",
                    metadata=metadata,
                )
            )
        self._events = events
        return input_tokens, cached_input_tokens, output_tokens


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None
