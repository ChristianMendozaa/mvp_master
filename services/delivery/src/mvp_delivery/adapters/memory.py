from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from mvp_delivery.application.ports import DeliveryRepository, EnrollmentTokenRecord
from mvp_delivery.domain.models import (
    AgentProviderConfiguration,
    Execution,
    ExecutionEvent,
    Runner,
)


class MemoryDeliveryRepository(DeliveryRepository):
    def __init__(self) -> None:
        self.provider_configurations: dict[UUID, AgentProviderConfiguration] = {}
        self.enrollment_tokens: dict[str, EnrollmentTokenRecord] = {}
        self.runners: dict[UUID, Runner] = {}
        self.executions: dict[UUID, Execution] = {}
        self.work_item_executions: dict[tuple[UUID, UUID], UUID] = {}
        self.events: dict[UUID, list[ExecutionEvent]] = {}
        self.audits: list[dict[str, object]] = []

    async def add_provider_configuration(self, configuration: AgentProviderConfiguration) -> None:
        self.provider_configurations[configuration.id] = configuration

    async def get_provider_configuration(
        self, organization_id: UUID, configuration_id: UUID
    ) -> AgentProviderConfiguration | None:
        configuration = self.provider_configurations.get(configuration_id)
        return (
            configuration
            if configuration and configuration.organization_id == organization_id
            else None
        )

    async def add_enrollment_token(self, record: EnrollmentTokenRecord) -> None:
        self.enrollment_tokens[record.token_hash] = record

    async def consume_enrollment_token(
        self, token_hash: str, now: datetime
    ) -> EnrollmentTokenRecord | None:
        record = self.enrollment_tokens.get(token_hash)
        if record is None or record.used_at is not None or record.expires_at <= now:
            return None
        self.enrollment_tokens[token_hash] = replace(record, used_at=datetime.now(UTC))
        return record

    async def add_runner(self, runner: Runner) -> None:
        self.runners[runner.id] = runner

    async def get_runner(self, organization_id: UUID, runner_id: UUID) -> Runner | None:
        runner = self.runners.get(runner_id)
        return runner if runner and runner.organization_id == organization_id else None

    async def add_execution(self, execution: Execution) -> bool:
        key = (execution.organization_id, execution.work_item_id)
        if key in self.work_item_executions:
            return False
        self.executions[execution.id] = execution
        self.work_item_executions[key] = execution.id
        return True

    async def get_execution(self, organization_id: UUID, execution_id: UUID) -> Execution | None:
        execution = self.executions.get(execution_id)
        return execution if execution and execution.organization_id == organization_id else None

    async def get_execution_by_work_item(
        self, organization_id: UUID, work_item_id: UUID
    ) -> Execution | None:
        execution_id = self.work_item_executions.get((organization_id, work_item_id))
        return self.executions.get(execution_id) if execution_id else None

    async def update_execution(self, execution: Execution) -> None:
        self.executions[execution.id] = execution

    async def append_event(self, event: ExecutionEvent) -> None:
        self.events.setdefault(event.execution_id, []).append(event)

    async def list_events(
        self, organization_id: UUID, execution_id: UUID, after_sequence: int
    ) -> tuple[ExecutionEvent, ...]:
        execution = await self.get_execution(organization_id, execution_id)
        if execution is None:
            return ()
        return tuple(
            event for event in self.events.get(execution_id, []) if event.sequence > after_sequence
        )

    async def next_event_sequence(self, execution_id: UUID) -> int:
        return len(self.events.get(execution_id, [])) + 1

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        self.audits.append(
            {
                "organization_id": organization_id,
                "actor_subject": actor_subject,
                "action": action,
                "target_id": target_id,
                "details": details,
            }
        )


class MemoryWorkflowGateway:
    def __init__(self) -> None:
        self.started: list[UUID] = []
        self.approved: list[tuple[UUID, str]] = []
        self.cancelled: list[tuple[UUID, str]] = []

    async def start(self, execution: Execution) -> None:
        if execution.id not in self.started:
            self.started.append(execution.id)

    async def approve(self, execution_id: UUID, actor_subject: str) -> None:
        self.approved.append((execution_id, actor_subject))

    async def cancel(self, execution_id: UUID, actor_subject: str) -> None:
        self.cancelled.append((execution_id, actor_subject))
