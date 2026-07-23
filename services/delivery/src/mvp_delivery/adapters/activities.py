import asyncio
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from mvp_common.contracts import ExternalReference
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio import activity

from mvp_delivery.adapters.postgres import PostgresDeliveryRepository
from mvp_delivery.adapters.temporal_workflow import DeliveryWorkflowInput
from mvp_delivery.domain.models import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionStatus,
)
from mvp_delivery.settings import Settings


class DeliveryActivities:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    @activity.defn(name="record-workflow-waiting")
    async def record_waiting(self, input: DeliveryWorkflowInput) -> None:
        del input

    @activity.defn(name="cancel-and-cleanup-execution")
    async def cancel_execution(self, input: DeliveryWorkflowInput) -> None:
        async with self._sessions() as session:
            repository = PostgresDeliveryRepository(session)
            execution = await repository.get_execution(
                UUID(input.organization_id), UUID(input.execution_id)
            )
            if execution and execution.cancellation_requested:
                execution.cancel()
                await repository.update_execution(execution)
                await self._event(
                    repository,
                    execution.id,
                    execution.organization_id,
                    ExecutionEventKind.STATE,
                    "execution.cancelled",
                    "Execution was cancelled and cleanup was requested.",
                )
                await session.commit()

    @activity.defn(name="execute-delivery")
    async def execute_delivery(self, input: DeliveryWorkflowInput) -> str:
        organization_id = UUID(input.organization_id)
        execution_id = UUID(input.execution_id)
        await self._enqueue(organization_id, execution_id)
        while True:
            activity.heartbeat("waiting for runner completion")
            async with self._sessions() as session:
                repository = PostgresDeliveryRepository(session)
                execution = await repository.get_execution(organization_id, execution_id)
                job = await repository.runner_job_for_execution(organization_id, execution_id)
                if execution is None or job is None:
                    raise RuntimeError("execution job disappeared")
                if job.status != "COMPLETED":
                    await asyncio.sleep(1)
                    continue
                result = cast(dict[str, Any], job.result or {})
                agent = cast(dict[str, Any], result.get("agent", {}))
                validation = cast(dict[str, Any], result.get("validation", {}))
                execution.record_usage(
                    attempts=1,
                    turns=int(agent.get("turns", 0)),
                    duration_seconds=int(result.get("duration_seconds", 0)),
                    cost_minor=int(result.get("cost_minor", 0)),
                )
                execution.start_verification()
                await repository.update_execution(execution)
                for item in list(agent.get("events", [])):
                    event = dict(item)
                    await self._event(
                        repository,
                        execution.id,
                        execution.organization_id,
                        ExecutionEventKind(str(event.get("kind", "TOOL"))),
                        str(event.get("name", "agent.event")),
                        str(event.get("message", "Agent emitted an event.")),
                    )
                await self._event(
                    repository,
                    execution.id,
                    execution.organization_id,
                    ExecutionEventKind.RESULT,
                    "verification.completed",
                    (
                        "Agent completed and independent verification passed."
                        if bool(agent.get("success")) and bool(validation.get("passed"))
                        else (
                            "Delivery evidence failed: the agent or independent "
                            "verification did not pass."
                        )
                    ),
                )
                if not bool(agent.get("success")) or not bool(validation.get("passed")):
                    execution.request_repair()
                    if execution.status is ExecutionStatus.REPAIRING:
                        execution.start_building()
                        job.status = "QUEUED"
                        job.result = None
                        job.leased_by_runner_id = None
                        job.leased_at = None
                        await repository.update_execution(execution)
                        await self._event(
                            repository,
                            execution.id,
                            execution.organization_id,
                            ExecutionEventKind.DECISION,
                            "repair.queued",
                            "Verification failed; a bounded repair attempt was queued.",
                        )
                        await session.commit()
                        continue
                    await repository.update_execution(execution)
                    await session.commit()
                    return execution.status.value
                execution.start_delivery()
                await repository.update_execution(execution)
                await session.commit()
            reference = await self._create_pull_request(
                organization_id=organization_id,
                execution_id=execution_id,
                repository_connection_id=execution.repository_connection_id,
                title=execution.title,
                commit_sha=str(result.get("commit_sha", "unknown")),
            )
            async with self._sessions() as session:
                repository = PostgresDeliveryRepository(session)
                delivered = await repository.get_execution(organization_id, execution_id)
                if delivered is None:
                    raise RuntimeError("execution disappeared during delivery")
                delivered.deliver(reference)
                await repository.update_execution(delivered)
                await self._event(
                    repository,
                    delivered.id,
                    delivered.organization_id,
                    ExecutionEventKind.RESULT,
                    "delivery.completed",
                    "Verified changes were associated with a pull request.",
                )
                await session.commit()
                return delivered.status.value

    async def _enqueue(self, organization_id: UUID, execution_id: UUID) -> None:
        async with self._sessions() as session:
            repository = PostgresDeliveryRepository(session)
            execution = await repository.get_execution(organization_id, execution_id)
            if execution is None:
                raise RuntimeError("execution not found")
            configuration = await repository.get_provider_configuration(
                organization_id, execution.provider_configuration_id
            )
            if configuration is None:
                raise RuntimeError("provider configuration not found")
            if execution.status is ExecutionStatus.QUEUED:
                execution.start_provisioning()
                execution.start_planning()
                execution.start_building()
                await repository.update_execution(execution)
            await repository.create_runner_job(
                execution,
                {
                    "execution_id": str(execution.id),
                    "organization_id": str(execution.organization_id),
                    "runtime": configuration.runtime,
                    "model": configuration.model,
                    "authentication_mode": configuration.authentication_mode.value,
                    "secret_reference": (
                        configuration.secret_reference.model_dump()
                        if configuration.secret_reference
                        else None
                    ),
                    "title": execution.title,
                    "problem": execution.description,
                    "acceptance_criteria": list(execution.acceptance_criteria),
                    "max_turns": execution.budget.max_turns,
                    "max_duration_seconds": execution.budget.max_duration_seconds,
                    "validation_commands": [
                        {
                            "executable": "python",
                            "arguments": ["verify.py"],
                            "timeout_seconds": 30,
                        }
                    ],
                },
            )
            await self._event(
                repository,
                execution.id,
                execution.organization_id,
                ExecutionEventKind.STATE,
                "runner.job_queued",
                "An isolated runner job was queued without credential values.",
            )
            await session.commit()

    async def _create_pull_request(
        self,
        *,
        organization_id: UUID,
        execution_id: UUID,
        repository_connection_id: UUID,
        title: str,
        commit_sha: str,
    ) -> ExternalReference:
        async with httpx.AsyncClient(
            base_url=self._settings.integrations_url, timeout=30
        ) as client:
            response = await client.post(
                "/internal/v1/pull-requests",
                headers={"X-Internal-Service-Token": self._settings.internal_service_token},
                json={
                    "organization_id": str(organization_id),
                    "repository_id": str(repository_connection_id),
                    "title": title,
                    "body": (
                        "Independently verified by MVP Master.\n\n"
                        f"Execution: {execution_id}\nCommit: {commit_sha}"
                    ),
                    "head_branch": f"agent/{str(execution_id)[:12]}",
                    "idempotency_key": str(execution_id),
                },
            )
            response.raise_for_status()
            payload = response.json()
            return ExternalReference(**payload["reference"])

    @staticmethod
    async def _event(
        repository: PostgresDeliveryRepository,
        execution_id: UUID,
        organization_id: UUID,
        kind: ExecutionEventKind,
        name: str,
        message: str,
    ) -> None:
        await repository.append_event(
            ExecutionEvent(
                id=uuid4(),
                execution_id=execution_id,
                organization_id=organization_id,
                sequence=await repository.next_event_sequence(execution_id),
                kind=kind,
                name=name,
                message=message,
            )
        )
