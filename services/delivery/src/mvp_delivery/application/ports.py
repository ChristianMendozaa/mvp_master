from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mvp_common.contracts import ExternalReference

from mvp_delivery.domain.models import (
    AgentProviderConfiguration,
    Execution,
    ExecutionEvent,
    Runner,
)


@dataclass(frozen=True, slots=True)
class EnrollmentTokenRecord:
    id: UUID
    organization_id: UUID
    pool_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None


@dataclass(frozen=True, slots=True)
class RunnerJob:
    id: UUID
    execution_id: UUID
    organization_id: UUID
    work_item_id: UUID
    repository_connection_id: UUID
    provider_configuration_id: UUID
    max_duration_seconds: int
    max_turns: int
    credential_lease_id: UUID
    idempotency_key: str


class DeliveryRepository(Protocol):
    async def add_provider_configuration(
        self, configuration: AgentProviderConfiguration
    ) -> None: ...

    async def get_provider_configuration(
        self, organization_id: UUID, configuration_id: UUID
    ) -> AgentProviderConfiguration | None: ...

    async def add_enrollment_token(self, record: EnrollmentTokenRecord) -> None: ...

    async def consume_enrollment_token(
        self, token_hash: str, now: datetime
    ) -> EnrollmentTokenRecord | None: ...

    async def add_runner(self, runner: Runner) -> None: ...

    async def get_runner(self, organization_id: UUID, runner_id: UUID) -> Runner | None: ...

    async def add_execution(self, execution: Execution) -> bool: ...

    async def get_execution(
        self, organization_id: UUID, execution_id: UUID
    ) -> Execution | None: ...

    async def get_execution_by_work_item(
        self, organization_id: UUID, work_item_id: UUID
    ) -> Execution | None: ...

    async def update_execution(self, execution: Execution) -> None: ...

    async def append_event(self, event: ExecutionEvent) -> None: ...

    async def list_events(
        self, organization_id: UUID, execution_id: UUID, after_sequence: int
    ) -> tuple[ExecutionEvent, ...]: ...

    async def next_event_sequence(self, execution_id: UUID) -> int: ...

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None: ...


class WorkflowGateway(Protocol):
    async def start(self, execution: Execution) -> None: ...

    async def approve(self, execution_id: UUID, actor_subject: str) -> None: ...

    async def cancel(self, execution_id: UUID, actor_subject: str) -> None: ...


class RunnerGateway(Protocol):
    async def dispatch(self, job: RunnerJob) -> None: ...


class PullRequestGateway(Protocol):
    async def create_pull_request(
        self,
        *,
        organization_id: UUID,
        repository_connection_id: UUID,
        title: str,
        body: str,
        head_branch: str,
        idempotency_key: str,
    ) -> ExternalReference: ...
