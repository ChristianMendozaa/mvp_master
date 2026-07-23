import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from mvp_common.contracts import SecretReference

from mvp_delivery.application.ports import (
    DeliveryRepository,
    EnrollmentTokenRecord,
    WorkflowGateway,
)
from mvp_delivery.domain.errors import InvalidEnrollment
from mvp_delivery.domain.models import (
    AgentProviderConfiguration,
    ApprovalStatus,
    AuthenticationMode,
    Execution,
    ExecutionBudget,
    ExecutionEvent,
    ExecutionEventKind,
    Runner,
)


class DeliveryService:
    def __init__(self, repository: DeliveryRepository, workflows: WorkflowGateway) -> None:
        self._repository = repository
        self._workflows = workflows

    async def create_provider_configuration(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        display_name: str,
        provider: str,
        runtime: str,
        model: str,
        authentication_mode: AuthenticationMode,
        secret_reference: SecretReference | None,
        is_development_substitute: bool,
    ) -> AgentProviderConfiguration:
        configuration = AgentProviderConfiguration(
            id=uuid4(),
            organization_id=organization_id,
            display_name=display_name,
            provider=provider,
            runtime=runtime,
            model=model,
            authentication_mode=authentication_mode,
            secret_reference=secret_reference,
            enabled=True,
            is_development_substitute=is_development_substitute,
        )
        await self._repository.add_provider_configuration(configuration)
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="provider_configuration.created",
            target_id=configuration.id,
            details={
                "provider": provider,
                "runtime": runtime,
                "model": model,
                "authentication_mode": authentication_mode.value,
                "development_substitute": is_development_substitute,
            },
        )
        return configuration

    async def create_runner_enrollment(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        pool_id: UUID,
    ) -> str:
        raw_token = secrets.token_urlsafe(32)
        record = EnrollmentTokenRecord(
            id=uuid4(),
            organization_id=organization_id,
            pool_id=pool_id,
            token_hash=self._hash(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            used_at=None,
        )
        await self._repository.add_enrollment_token(record)
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="runner.enrollment_created",
            target_id=record.id,
            details={"pool_id": str(pool_id), "expires_in_seconds": 600},
        )
        return raw_token

    async def enroll_runner(
        self,
        *,
        enrollment_token: str,
        name: str,
        capabilities: tuple[str, ...],
    ) -> tuple[Runner, str]:
        record = await self._repository.consume_enrollment_token(
            self._hash(enrollment_token), datetime.now(UTC)
        )
        if record is None:
            raise InvalidEnrollment("enrollment token is invalid, expired, or already used")
        raw_credential = secrets.token_urlsafe(48)
        runner = Runner(
            id=uuid4(),
            organization_id=record.organization_id,
            pool_id=record.pool_id,
            name=name,
            capabilities=capabilities,
            credential_hash=self._hash(raw_credential),
        )
        await self._repository.add_runner(runner)
        await self._repository.record_audit(
            organization_id=record.organization_id,
            actor_subject=f"runner-enrollment:{record.id}",
            action="runner.enrolled",
            target_id=runner.id,
            details={"pool_id": str(record.pool_id), "capabilities": list(capabilities)},
        )
        return runner, raw_credential

    async def accept_ready_work_item(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        work_item_id: UUID,
        title: str,
        description: str,
        acceptance_criteria: tuple[str, ...],
        repository_connection_id: UUID,
        provider_configuration_id: UUID,
        runner_pool_id: UUID,
        budget: ExecutionBudget,
        correlation_id: UUID,
    ) -> Execution:
        existing = await self._repository.get_execution_by_work_item(organization_id, work_item_id)
        if existing is not None:
            return existing
        if (
            await self._repository.get_provider_configuration(
                organization_id, provider_configuration_id
            )
            is None
        ):
            raise ValueError("provider configuration is not available to this organization")
        execution = Execution(
            id=uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            work_item_id=work_item_id,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            repository_connection_id=repository_connection_id,
            provider_configuration_id=provider_configuration_id,
            runner_pool_id=runner_pool_id,
            budget=budget,
            approval_status=ApprovalStatus.PENDING,
        )
        if await self._repository.add_execution(execution):
            await self._append_event(
                execution,
                ExecutionEventKind.APPROVAL,
                "execution.approval_required",
                "Execution is waiting for reviewer approval.",
                {"correlation_id": str(correlation_id)},
            )
            await self._workflows.start(execution)
        return execution

    async def approve_execution(
        self,
        *,
        organization_id: UUID,
        execution_id: UUID,
        actor_subject: str,
    ) -> Execution:
        execution = await self._required_execution(organization_id, execution_id)
        execution.approve()
        await self._repository.update_execution(execution)
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="execution.approved",
            target_id=execution.id,
            details={"version": execution.version},
        )
        await self._append_event(
            execution,
            ExecutionEventKind.APPROVAL,
            "execution.approved",
            "Execution was approved and queued.",
            {"actor_subject": actor_subject},
        )
        await self._workflows.approve(execution.id, actor_subject)
        return execution

    async def cancel_execution(
        self,
        *,
        organization_id: UUID,
        execution_id: UUID,
        actor_subject: str,
    ) -> Execution:
        execution = await self._required_execution(organization_id, execution_id)
        execution.request_cancellation()
        await self._repository.update_execution(execution)
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="execution.cancellation_requested",
            target_id=execution.id,
            details={"version": execution.version},
        )
        await self._workflows.cancel(execution.id, actor_subject)
        return execution

    async def _required_execution(self, organization_id: UUID, execution_id: UUID) -> Execution:
        execution = await self._repository.get_execution(organization_id, execution_id)
        if execution is None:
            raise LookupError("execution not found")
        return execution

    async def _append_event(
        self,
        execution: Execution,
        kind: ExecutionEventKind,
        name: str,
        message: str,
        metadata: dict[str, str | int | bool | None],
    ) -> None:
        await self._repository.append_event(
            ExecutionEvent(
                id=uuid4(),
                execution_id=execution.id,
                organization_id=execution.organization_id,
                sequence=await self._repository.next_event_sequence(execution.id),
                kind=kind,
                name=name,
                message=message,
                metadata=metadata,
            )
        )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
