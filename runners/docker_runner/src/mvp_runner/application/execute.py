from pathlib import PurePosixPath
from uuid import UUID

from mvp_common.contracts import SecretReference

from mvp_runner.application.ports import AgentRuntime, Validator, WorkspaceManager
from mvp_runner.domain.models import (
    AgentRequest,
    AgentResult,
    ValidationCommand,
    ValidationResult,
)


class RunnerExecutionService:
    def __init__(
        self,
        *,
        agents: dict[str, AgentRuntime],
        validator: Validator,
        workspaces: WorkspaceManager,
    ) -> None:
        self._agents = agents
        self._validator = validator
        self._workspaces = workspaces

    async def execute(
        self,
        *,
        execution_id: UUID,
        organization_id: UUID,
        runtime: str,
        model: str,
        authentication_mode: str,
        secret_reference: SecretReference | None,
        title: str,
        problem: str,
        acceptance_criteria: tuple[str, ...],
        max_turns: int,
        max_duration_seconds: int,
        validation_commands: tuple[ValidationCommand, ...],
        keep_failed_workspace: bool = False,
    ) -> tuple[AgentResult, ValidationResult]:
        agent = self._agents[runtime]
        if not await agent.available():
            raise RuntimeError(f"agent runtime {runtime!r} is not available")
        workspace = await self._workspaces.provision(str(execution_id))
        try:
            result = await agent.execute(
                AgentRequest(
                    execution_id=execution_id,
                    organization_id=organization_id,
                    model=model,
                    authentication_mode=authentication_mode,
                    secret_reference=secret_reference,
                    workspace=PurePosixPath(workspace),
                    title=title,
                    problem=problem,
                    acceptance_criteria=acceptance_criteria,
                    max_turns=max_turns,
                    max_duration_seconds=max_duration_seconds,
                )
            )
            validation = await self._validator.validate(
                workspace=workspace, commands=validation_commands
            )
            return result, validation
        finally:
            if not keep_failed_workspace:
                await self._workspaces.cleanup(str(execution_id))
