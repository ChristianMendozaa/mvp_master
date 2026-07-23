import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from mvp_runner.domain.models import (
    AgentCapabilities,
    AgentEvent,
    AgentEventKind,
    AgentRequest,
    AgentResult,
)


class DeterministicAgent:
    name = "deterministic"
    is_development_substitute = True

    def __init__(self) -> None:
        self._events: list[AgentEvent] = []
        self._cancelled = False

    async def available(self) -> bool:
        return True

    async def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_resume=False,
            supports_structured_events=True,
            supports_usage=True,
            supports_approval=False,
            supported_authentication_modes=("NONE",),
        )

    async def execute(self, request: AgentRequest) -> AgentResult:
        self._events = [
            AgentEvent(
                sequence=1,
                kind=AgentEventKind.PLAN,
                name="plan.created",
                message="Update the fixture status card and its deterministic assertion.",
            )
        ]
        if self._cancelled:
            raise asyncio.CancelledError
        workspace = Path(request.workspace)
        target, resolved_workspace = await asyncio.to_thread(
            lambda: ((workspace / "src" / "status.json").resolve(), workspace.resolve())
        )
        if not target.is_relative_to(resolved_workspace):
            raise ValueError("target escaped workspace")
        current = json.loads(await asyncio.to_thread(target.read_text, encoding="utf-8"))
        current["title"] = request.title
        current["status"] = "Delivered by deterministic local agent"
        await asyncio.to_thread(
            target.write_text,
            json.dumps(current, indent=2) + "\n",
            encoding="utf-8",
        )
        self._events.extend(
            (
                AgentEvent(
                    sequence=2,
                    kind=AgentEventKind.TOOL,
                    name="file.updated",
                    message="Updated src/status.json in the isolated workspace.",
                    metadata={"path": "src/status.json"},
                ),
                AgentEvent(
                    sequence=3,
                    kind=AgentEventKind.RESULT,
                    name="agent.completed",
                    message=(
                        "Deterministic fixture change completed; independent validation is pending."
                    ),
                ),
            )
        )
        return AgentResult(
            success=True,
            summary="Updated the delivery status fixture.",
            session_id=None,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            turns=1,
            changed_paths=("src/status.json",),
            events=tuple(self._events),
        )

    async def stream(self) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event

    async def cancel(self) -> None:
        self._cancelled = True
