from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from mvp_common.contracts import SecretReference

from mvp_runner.domain.models import (
    AgentCapabilities,
    AgentEvent,
    AgentRequest,
    AgentResult,
    ValidationCommand,
    ValidationResult,
)


class AgentRuntime(Protocol):
    name: str
    is_development_substitute: bool

    async def available(self) -> bool: ...

    async def capabilities(self) -> AgentCapabilities: ...

    async def execute(self, request: AgentRequest) -> AgentResult: ...

    async def stream(self) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self) -> None: ...


class Validator(Protocol):
    async def validate(
        self, *, workspace: Path, commands: tuple[ValidationCommand, ...]
    ) -> ValidationResult: ...


class SecretResolver(Protocol):
    async def resolve(self, reference: SecretReference) -> str: ...


class WorkspaceManager(Protocol):
    async def provision(self, execution_id: str) -> Path: ...

    async def cleanup(self, execution_id: str) -> None: ...
