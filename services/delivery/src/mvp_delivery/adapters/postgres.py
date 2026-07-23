import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mvp_common.contracts import ExternalReference, SecretReference
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, or_
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import select, text

from mvp_delivery.application.ports import DeliveryRepository, EnrollmentTokenRecord
from mvp_delivery.domain.models import (
    AgentProviderConfiguration,
    ApprovalStatus,
    AuthenticationMode,
    Execution,
    ExecutionBudget,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionStatus,
    Runner,
    RunnerStatus,
)


class Base(DeclarativeBase):
    pass


class MembershipProjectionRow(Base):
    __tablename__ = "membership_projection"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(String(300), primary_key=True)
    role: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean)


class ProviderConfigurationRow(Base):
    __tablename__ = "provider_configurations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(64))
    runtime: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(200))
    authentication_mode: Mapped[str] = mapped_column(String(64))
    secret_reference: Mapped[dict[str, str | None] | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean)
    is_development_substitute: Mapped[bool] = mapped_column(Boolean)


class RunnerPoolRow(Base):
    __tablename__ = "runner_pools"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(200))
    runner_type: Mapped[str] = mapped_column(String(64))


class EnrollmentTokenRow(Base):
    __tablename__ = "runner_enrollment_tokens"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    pool_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnrollmentRoutingRow(Base):
    __tablename__ = "runner_enrollment_routing"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))


class RunnerRow(Base):
    __tablename__ = "runners"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    pool_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(200))
    capabilities: Mapped[list[str]] = mapped_column(JSON)
    credential_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunnerCredentialRoutingRow(Base):
    __tablename__ = "runner_credential_routing"
    credential_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    runner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class ExecutionRow(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("organization_id", "work_item_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    work_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON)
    repository_connection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    provider_configuration_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    runner_pool_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    budget: Mapped[dict[str, int | str]] = mapped_column(JSON)
    approval_status: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer)
    turn_count: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    cost_minor: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean)
    result_reference: Mapped[dict[str, str | None] | None] = mapped_column(JSON)


class ExecutionEventRow(Base):
    __tablename__ = "execution_events"
    __table_args__ = (UniqueConstraint("execution_id", "sequence"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_metadata: Mapped[dict[str, str | int | bool | None]] = mapped_column(JSON)


class RunnerJobRow(Base):
    __tablename__ = "runner_jobs"
    __table_args__ = (UniqueConstraint("organization_id", "execution_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    pool_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    leased_by_runner_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(128))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InboxRow(Base):
    __tablename__ = "event_inbox"
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(200))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class WorkflowCommandRow(Base):
    __tablename__ = "workflow_commands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    command: Mapped[str] = mapped_column(String(32))
    actor_subject: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PostgresDeliveryRepository(DeliveryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_organization(self, organization_id: UUID) -> None:
        await self._session.execute(
            text("select set_config('app.current_organization_id', :value, true)"),
            {"value": str(organization_id)},
        )

    async def role_for(self, organization_id: UUID, subject: str) -> str | None:
        await self.set_organization(organization_id)
        value: str | None = await self._session.scalar(
            select(MembershipProjectionRow.role).where(
                MembershipProjectionRow.organization_id == organization_id,
                MembershipProjectionRow.subject == subject,
                MembershipProjectionRow.active.is_(True),
            )
        )
        return value

    async def upsert_membership(
        self, organization_id: UUID, subject: str, role: str, active: bool
    ) -> None:
        await self.set_organization(organization_id)
        row = await self._session.get(MembershipProjectionRow, (organization_id, subject))
        if row:
            row.role = role
            row.active = active
        else:
            self._session.add(
                MembershipProjectionRow(
                    organization_id=organization_id,
                    subject=subject,
                    role=role,
                    active=active,
                )
            )

    async def record_inbox(self, event_id: UUID, organization_id: UUID, event_type: str) -> bool:
        await self.set_organization(organization_id)
        if await self._session.get(InboxRow, event_id):
            return False
        self._session.add(
            InboxRow(
                event_id=event_id,
                organization_id=organization_id,
                event_type=event_type,
            )
        )
        return True

    async def add_provider_configuration(self, configuration: AgentProviderConfiguration) -> None:
        await self.set_organization(configuration.organization_id)
        self._session.add(
            ProviderConfigurationRow(
                id=configuration.id,
                organization_id=configuration.organization_id,
                display_name=configuration.display_name,
                provider=configuration.provider,
                runtime=configuration.runtime,
                model=configuration.model,
                authentication_mode=configuration.authentication_mode.value,
                secret_reference=(
                    configuration.secret_reference.model_dump()
                    if configuration.secret_reference
                    else None
                ),
                enabled=configuration.enabled,
                is_development_substitute=configuration.is_development_substitute,
            )
        )

    async def get_provider_configuration(
        self, organization_id: UUID, configuration_id: UUID
    ) -> AgentProviderConfiguration | None:
        await self.set_organization(organization_id)
        row = await self._session.get(ProviderConfigurationRow, configuration_id)
        if row is None:
            return None
        return AgentProviderConfiguration(
            id=row.id,
            organization_id=row.organization_id,
            display_name=row.display_name,
            provider=row.provider,
            runtime=row.runtime,
            model=row.model,
            authentication_mode=AuthenticationMode(row.authentication_mode),
            secret_reference=(
                SecretReference(**row.secret_reference) if row.secret_reference else None
            ),
            enabled=row.enabled,
            is_development_substitute=row.is_development_substitute,
        )

    async def list_provider_configurations(
        self, organization_id: UUID
    ) -> tuple[AgentProviderConfiguration, ...]:
        await self.set_organization(organization_id)
        rows = (await self._session.scalars(select(ProviderConfigurationRow))).all()
        result: list[AgentProviderConfiguration] = []
        for row in rows:
            item = await self.get_provider_configuration(organization_id, row.id)
            if item:
                result.append(item)
        return tuple(result)

    async def add_runner_pool(
        self, organization_id: UUID, pool_id: UUID, name: str, runner_type: str
    ) -> None:
        await self.set_organization(organization_id)
        self._session.add(
            RunnerPoolRow(
                id=pool_id,
                organization_id=organization_id,
                name=name,
                runner_type=runner_type,
            )
        )

    async def list_runner_pools(self, organization_id: UUID) -> tuple[dict[str, str], ...]:
        await self.set_organization(organization_id)
        rows = (await self._session.scalars(select(RunnerPoolRow))).all()
        return tuple(
            {"id": str(row.id), "name": row.name, "runner_type": row.runner_type} for row in rows
        )

    async def add_enrollment_token(self, record: EnrollmentTokenRecord) -> None:
        await self.set_organization(record.organization_id)
        self._session.add(
            EnrollmentTokenRow(
                id=record.id,
                organization_id=record.organization_id,
                pool_id=record.pool_id,
                token_hash=record.token_hash,
                expires_at=record.expires_at,
                used_at=record.used_at,
            )
        )
        self._session.add(
            EnrollmentRoutingRow(
                token_hash=record.token_hash, organization_id=record.organization_id
            )
        )

    async def consume_enrollment_token(
        self, token_hash: str, now: datetime
    ) -> EnrollmentTokenRecord | None:
        organization_id = await self._session.scalar(
            select(EnrollmentRoutingRow.organization_id).where(
                EnrollmentRoutingRow.token_hash == token_hash
            )
        )
        if organization_id is None:
            return None
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(EnrollmentTokenRow)
            .where(EnrollmentTokenRow.token_hash == token_hash)
            .with_for_update()
        )
        if row is None or row.used_at is not None or row.expires_at <= now:
            return None
        record = EnrollmentTokenRecord(
            id=row.id,
            organization_id=row.organization_id,
            pool_id=row.pool_id,
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            used_at=row.used_at,
        )
        row.used_at = datetime.now(UTC)
        return record

    async def add_runner(self, runner: Runner) -> None:
        await self.set_organization(runner.organization_id)
        self._session.add(
            RunnerRow(
                id=runner.id,
                organization_id=runner.organization_id,
                pool_id=runner.pool_id,
                name=runner.name,
                capabilities=list(runner.capabilities),
                credential_hash=runner.credential_hash,
                status=runner.status.value,
                last_seen_at=runner.last_seen_at,
            )
        )
        self._session.add(
            RunnerCredentialRoutingRow(
                credential_hash=runner.credential_hash,
                organization_id=runner.organization_id,
                runner_id=runner.id,
            )
        )

    async def get_runner(self, organization_id: UUID, runner_id: UUID) -> Runner | None:
        await self.set_organization(organization_id)
        row = await self._session.get(RunnerRow, runner_id)
        return (
            Runner(
                id=row.id,
                organization_id=row.organization_id,
                pool_id=row.pool_id,
                name=row.name,
                capabilities=tuple(row.capabilities),
                credential_hash=row.credential_hash,
                status=RunnerStatus(row.status),
                last_seen_at=row.last_seen_at,
            )
            if row
            else None
        )

    async def authenticate_runner(self, runner_id: UUID, credential: str) -> Runner | None:
        credential_hash = hashlib.sha256(credential.encode()).hexdigest()
        route = await self._session.get(RunnerCredentialRoutingRow, credential_hash)
        if route is None or route.runner_id != runner_id:
            return None
        runner = await self.get_runner(route.organization_id, runner_id)
        if runner is None or not hmac.compare_digest(runner.credential_hash, credential_hash):
            return None
        return runner

    async def create_runner_job(
        self, execution: Execution, payload: dict[str, object]
    ) -> RunnerJobRow:
        await self.set_organization(execution.organization_id)
        existing = await self._session.scalar(
            select(RunnerJobRow).where(RunnerJobRow.execution_id == execution.id)
        )
        if existing:
            return existing
        row = RunnerJobRow(
            id=UUID(int=execution.id.int ^ 1),
            organization_id=execution.organization_id,
            execution_id=execution.id,
            pool_id=execution.runner_pool_id,
            status="QUEUED",
            payload=payload,
            result=None,
            leased_by_runner_id=None,
            leased_at=None,
            completed_at=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def lease_runner_job(self, runner: Runner) -> RunnerJobRow | None:
        await self.set_organization(runner.organization_id)
        stale_before = datetime.now(UTC) - timedelta(seconds=45)
        row = await self._session.scalar(
            select(RunnerJobRow)
            .where(
                RunnerJobRow.pool_id == runner.pool_id,
                or_(
                    RunnerJobRow.status == "QUEUED",
                    ((RunnerJobRow.status == "LEASED") & (RunnerJobRow.leased_at < stale_before)),
                ),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row:
            row.status = "LEASED"
            row.leased_by_runner_id = runner.id
            row.leased_at = datetime.now(UTC)
        return row

    async def heartbeat_runner_job(self, runner: Runner, job_id: UUID) -> RunnerJobRow | None:
        await self.set_organization(runner.organization_id)
        row = await self._session.get(RunnerJobRow, job_id)
        if row is None or row.leased_by_runner_id != runner.id or row.status != "LEASED":
            return None
        row.leased_at = datetime.now(UTC)
        return row

    async def complete_runner_job(
        self, runner: Runner, job_id: UUID, result: dict[str, object]
    ) -> RunnerJobRow | None:
        await self.set_organization(runner.organization_id)
        row = await self._session.get(RunnerJobRow, job_id)
        if row is None or row.leased_by_runner_id != runner.id or row.status != "LEASED":
            return None
        row.result = result
        row.status = "COMPLETED"
        row.completed_at = datetime.now(UTC)
        return row

    async def runner_job_for_execution(
        self, organization_id: UUID, execution_id: UUID
    ) -> RunnerJobRow | None:
        await self.set_organization(organization_id)
        value: RunnerJobRow | None = await self._session.scalar(
            select(RunnerJobRow).where(RunnerJobRow.execution_id == execution_id)
        )
        return value

    async def add_execution(self, execution: Execution) -> bool:
        await self.set_organization(execution.organization_id)
        existing = await self.get_execution_by_work_item(
            execution.organization_id, execution.work_item_id
        )
        if existing:
            return False
        self._session.add(self._execution_row(execution))
        return True

    async def get_execution(self, organization_id: UUID, execution_id: UUID) -> Execution | None:
        await self.set_organization(organization_id)
        row = await self._session.get(ExecutionRow, execution_id)
        return self._execution(row) if row else None

    async def get_execution_by_work_item(
        self, organization_id: UUID, work_item_id: UUID
    ) -> Execution | None:
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(ExecutionRow).where(ExecutionRow.work_item_id == work_item_id)
        )
        return self._execution(row) if row else None

    async def update_execution(self, execution: Execution) -> None:
        await self.set_organization(execution.organization_id)
        row = await self._session.get(ExecutionRow, execution.id)
        if row:
            replacement = self._execution_row(execution)
            for attribute in (
                "approval_status",
                "status",
                "attempt_count",
                "turn_count",
                "duration_seconds",
                "cost_minor",
                "version",
                "cancellation_requested",
                "result_reference",
            ):
                setattr(row, attribute, getattr(replacement, attribute))

    async def list_executions(self, organization_id: UUID) -> tuple[Execution, ...]:
        await self.set_organization(organization_id)
        rows = (
            await self._session.scalars(
                select(ExecutionRow).order_by(ExecutionRow.id.desc()).limit(100)
            )
        ).all()
        return tuple(self._execution(row) for row in rows)

    async def append_event(self, event: ExecutionEvent) -> None:
        await self.set_organization(event.organization_id)
        self._session.add(
            ExecutionEventRow(
                id=event.id,
                execution_id=event.execution_id,
                organization_id=event.organization_id,
                sequence=event.sequence,
                kind=event.kind.value,
                name=event.name,
                message=event.message,
                occurred_at=event.occurred_at,
                event_metadata=event.metadata,
            )
        )

    async def list_events(
        self, organization_id: UUID, execution_id: UUID, after_sequence: int
    ) -> tuple[ExecutionEvent, ...]:
        await self.set_organization(organization_id)
        rows = (
            await self._session.scalars(
                select(ExecutionEventRow)
                .where(
                    ExecutionEventRow.execution_id == execution_id,
                    ExecutionEventRow.sequence > after_sequence,
                )
                .order_by(ExecutionEventRow.sequence)
            )
        ).all()
        return tuple(
            ExecutionEvent(
                id=row.id,
                execution_id=row.execution_id,
                organization_id=row.organization_id,
                sequence=row.sequence,
                kind=ExecutionEventKind(row.kind),
                name=row.name,
                message=row.message,
                occurred_at=row.occurred_at,
                metadata=row.event_metadata,
            )
            for row in rows
        )

    async def next_event_sequence(self, execution_id: UUID) -> int:
        current = await self._session.scalar(
            select(ExecutionEventRow.sequence)
            .where(ExecutionEventRow.execution_id == execution_id)
            .order_by(ExecutionEventRow.sequence.desc())
            .limit(1)
        )
        return (current or 0) + 1

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        await self.set_organization(organization_id)
        self._session.add(
            AuditRow(
                organization_id=organization_id,
                actor_subject=actor_subject,
                action=action,
                target_id=target_id,
                details=details,
            )
        )

    @staticmethod
    def _execution_row(execution: Execution) -> ExecutionRow:
        return ExecutionRow(
            id=execution.id,
            organization_id=execution.organization_id,
            project_id=execution.project_id,
            work_item_id=execution.work_item_id,
            title=execution.title,
            description=execution.description,
            acceptance_criteria=list(execution.acceptance_criteria),
            repository_connection_id=execution.repository_connection_id,
            provider_configuration_id=execution.provider_configuration_id,
            runner_pool_id=execution.runner_pool_id,
            budget={
                "max_duration_seconds": execution.budget.max_duration_seconds,
                "max_attempts": execution.budget.max_attempts,
                "max_turns": execution.budget.max_turns,
                "max_cost_minor": execution.budget.max_cost_minor,
                "currency": execution.budget.currency,
            },
            approval_status=execution.approval_status.value,
            status=execution.status.value,
            attempt_count=execution.attempt_count,
            turn_count=execution.turn_count,
            duration_seconds=execution.duration_seconds,
            cost_minor=execution.cost_minor,
            version=execution.version,
            cancellation_requested=execution.cancellation_requested,
            result_reference=(
                execution.result_reference.model_dump() if execution.result_reference else None
            ),
        )

    @staticmethod
    def _execution(row: ExecutionRow) -> Execution:
        budget = row.budget
        return Execution(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            work_item_id=row.work_item_id,
            title=row.title,
            description=row.description,
            acceptance_criteria=tuple(row.acceptance_criteria),
            repository_connection_id=row.repository_connection_id,
            provider_configuration_id=row.provider_configuration_id,
            runner_pool_id=row.runner_pool_id,
            budget=ExecutionBudget(
                max_duration_seconds=int(budget["max_duration_seconds"]),
                max_attempts=int(budget["max_attempts"]),
                max_turns=int(budget["max_turns"]),
                max_cost_minor=int(budget["max_cost_minor"]),
                currency=str(budget["currency"]),
            ),
            approval_status=ApprovalStatus(row.approval_status),
            status=ExecutionStatus(row.status),
            attempt_count=row.attempt_count,
            turn_count=row.turn_count,
            duration_seconds=row.duration_seconds,
            cost_minor=row.cost_minor,
            version=row.version,
            cancellation_requested=row.cancellation_requested,
            result_reference=(
                ExternalReference(**row.result_reference) if row.result_reference else None
            ),
        )


class PostgresWorkflowGateway:
    """Transactional workflow command outbox; a dispatcher talks to Temporal."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, execution: Execution) -> None:
        self._session.add(
            WorkflowCommandRow(
                organization_id=execution.organization_id,
                execution_id=execution.id,
                command="START",
                actor_subject=None,
            )
        )

    async def approve(self, execution_id: UUID, actor_subject: str) -> None:
        organization_id = await self._session.scalar(
            select(ExecutionRow.organization_id).where(ExecutionRow.id == execution_id)
        )
        if organization_id is None:
            raise LookupError("execution not found")
        self._session.add(
            WorkflowCommandRow(
                organization_id=organization_id,
                execution_id=execution_id,
                command="APPROVE",
                actor_subject=actor_subject,
            )
        )

    async def cancel(self, execution_id: UUID, actor_subject: str) -> None:
        organization_id = await self._session.scalar(
            select(ExecutionRow.organization_id).where(ExecutionRow.id == execution_id)
        )
        if organization_id is None:
            raise LookupError("execution not found")
        self._session.add(
            WorkflowCommandRow(
                organization_id=organization_id,
                execution_id=execution_id,
                command="CANCEL",
                actor_subject=actor_subject,
            )
        )
