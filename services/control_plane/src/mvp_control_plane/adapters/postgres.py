from dataclasses import asdict
from datetime import datetime
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from mvp_common.contracts import EventEnvelope
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import select, text

from mvp_control_plane.application.ports import ControlPlaneRepository
from mvp_control_plane.domain.models import (
    Approval,
    Budget,
    IntakeRequest,
    IntakeStatus,
    Organization,
    Project,
    Role,
    Specification,
    SpecificationStatus,
    SpecificationVersion,
    WorkItem,
    WorkItemStatus,
)


class Base(DeclarativeBase):
    pass


class OrganizationRow(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MembershipRow(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id"), primary_key=True
    )
    subject: Mapped[str] = mapped_column(String(300), primary_key=True)
    role: Mapped[str] = mapped_column(String(32))


class MembershipRoutingRow(Base):
    __tablename__ = "membership_routing"
    subject: Mapped[str] = mapped_column(String(300), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(32))


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    execution_approval_required: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntakeRow(Base):
    __tablename__ = "intake_requests"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    client_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(300))
    problem: Mapped[str] = mapped_column(Text)
    intended_users: Mapped[str] = mapped_column(Text)
    required_functionality: Mapped[list[str]] = mapped_column(JSON)
    exclusions: Mapped[list[str]] = mapped_column(JSON)
    constraints: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SpecificationRow(Base):
    __tablename__ = "specifications"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    intake_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    current_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    current_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64))


class SpecificationVersionRow(Base):
    __tablename__ = "specification_versions"
    __table_args__ = (UniqueConstraint("specification_id", "version"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    specification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    problem: Mapped[str] = mapped_column(Text)
    intended_users: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list[str]] = mapped_column(JSON)
    exclusions: Mapped[list[str]] = mapped_column(JSON)
    constraints: Mapped[list[str]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    subject_type: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    subject_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(32))
    actor_subject: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkItemRow(Base):
    __tablename__ = "work_items"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    specification_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64))
    repository_connection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_configuration_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    runner_pool_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    budget: Mapped[dict[str, object] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class OutboxRow(Base):
    __tablename__ = "event_outbox"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxRoutingRow(Base):
    __tablename__ = "event_outbox_routing"
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class PostgresControlPlaneRepository(ControlPlaneRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def role_for(self, organization_id: UUID, subject: str) -> Role | None:
        value = await self._session.scalar(
            select(MembershipRow.role).where(
                MembershipRow.organization_id == organization_id,
                MembershipRow.subject == subject,
            )
        )
        return Role(value) if value else None

    async def add_organization(self, organization: Organization, owner_subject: str) -> None:
        self._session.add(
            OrganizationRow(
                id=organization.id, name=organization.name, created_at=organization.created_at
            )
        )
        self._session.add(
            MembershipRow(
                organization_id=organization.id, subject=owner_subject, role=Role.OWNER.value
            )
        )
        self._session.add(
            MembershipRoutingRow(
                subject=owner_subject,
                organization_id=organization.id,
                role=Role.OWNER.value,
            )
        )

    async def list_organizations_for_subject(
        self, subject: str
    ) -> tuple[tuple[Organization, Role], ...]:
        routes = (
            await self._session.scalars(
                select(MembershipRoutingRow).where(MembershipRoutingRow.subject == subject)
            )
        ).all()
        result: list[tuple[Organization, Role]] = []
        for route in routes:
            await self._session.execute(
                text("select set_config('app.current_organization_id', :value, true)"),
                {"value": str(route.organization_id)},
            )
            organization = await self._session.get(OrganizationRow, route.organization_id)
            if organization:
                result.append(
                    (
                        Organization(
                            id=organization.id,
                            name=organization.name,
                            created_at=organization.created_at,
                        ),
                        Role(route.role),
                    )
                )
        return tuple(result)

    async def add_project(self, project: Project) -> None:
        self._session.add(ProjectRow(**asdict(project)))

    async def get_project(self, organization_id: UUID, project_id: UUID) -> Project | None:
        row = await self._session.scalar(
            select(ProjectRow).where(
                ProjectRow.organization_id == organization_id, ProjectRow.id == project_id
            )
        )
        return self._project(row) if row else None

    async def list_projects(self, organization_id: UUID) -> tuple[Project, ...]:
        rows = (
            await self._session.scalars(
                select(ProjectRow).where(ProjectRow.organization_id == organization_id)
            )
        ).all()
        return tuple(self._project(row) for row in rows)

    async def add_intake(self, intake: IntakeRequest) -> None:
        self._session.add(self._intake_row(intake))

    async def get_intake(self, organization_id: UUID, intake_id: UUID) -> IntakeRequest | None:
        row = await self._session.scalar(
            select(IntakeRow).where(
                IntakeRow.organization_id == organization_id, IntakeRow.id == intake_id
            )
        )
        return self._intake(row) if row else None

    async def update_intake(self, intake: IntakeRequest) -> None:
        row = await self._session.get(IntakeRow, intake.id)
        if row:
            row.status = intake.status.value

    async def list_intakes(self, organization_id: UUID) -> tuple[IntakeRequest, ...]:
        rows = (
            await self._session.scalars(
                select(IntakeRow).where(IntakeRow.organization_id == organization_id)
            )
        ).all()
        return tuple(self._intake(row) for row in rows)

    async def add_specification(
        self, specification: Specification, version: SpecificationVersion
    ) -> None:
        self._session.add(
            SpecificationRow(
                id=specification.id,
                organization_id=specification.organization_id,
                project_id=specification.project_id,
                intake_id=specification.intake_id,
                current_version_id=specification.current_version_id,
                current_version=specification.current_version,
                status=specification.status.value,
            )
        )
        self._session.add(
            SpecificationVersionRow(
                id=version.id,
                organization_id=specification.organization_id,
                specification_id=version.specification_id,
                version=version.version,
                title=version.title,
                problem=version.problem,
                intended_users=version.intended_users,
                requirements=list(version.requirements),
                exclusions=list(version.exclusions),
                constraints=list(version.constraints),
                created_by=version.created_by,
                created_at=version.created_at,
            )
        )

    async def get_specification(
        self, organization_id: UUID, specification_id: UUID
    ) -> Specification | None:
        row = await self._session.scalar(
            select(SpecificationRow).where(
                SpecificationRow.organization_id == organization_id,
                SpecificationRow.id == specification_id,
            )
        )
        return self._specification(row) if row else None

    async def get_specification_version(
        self, organization_id: UUID, version_id: UUID
    ) -> SpecificationVersion | None:
        row = await self._session.scalar(
            select(SpecificationVersionRow).where(
                SpecificationVersionRow.organization_id == organization_id,
                SpecificationVersionRow.id == version_id,
            )
        )
        return self._specification_version(row) if row else None

    async def update_specification(self, specification: Specification) -> None:
        row = await self._session.get(SpecificationRow, specification.id)
        if row:
            row.status = specification.status.value
            row.current_version = specification.current_version
            row.current_version_id = specification.current_version_id

    async def list_specifications(self, organization_id: UUID) -> tuple[Specification, ...]:
        rows = (
            await self._session.scalars(
                select(SpecificationRow).where(SpecificationRow.organization_id == organization_id)
            )
        ).all()
        return tuple(self._specification(row) for row in rows)

    async def add_approval(self, approval: Approval) -> None:
        self._session.add(ApprovalRow(**asdict(approval)))

    async def add_work_item(self, work_item: WorkItem) -> None:
        self._session.add(self._work_item_row(work_item))

    async def get_work_item(self, organization_id: UUID, work_item_id: UUID) -> WorkItem | None:
        row = await self._session.scalar(
            select(WorkItemRow).where(
                WorkItemRow.organization_id == organization_id, WorkItemRow.id == work_item_id
            )
        )
        return self._work_item(row) if row else None

    async def update_work_item(self, work_item: WorkItem) -> None:
        row = await self._session.get(WorkItemRow, work_item.id)
        if row:
            row.status = work_item.status.value
            row.repository_connection_id = work_item.repository_connection_id
            row.provider_configuration_id = work_item.provider_configuration_id
            row.runner_pool_id = work_item.runner_pool_id
            row.budget = asdict(work_item.budget) if work_item.budget else None
            row.version = work_item.version

    async def list_work_items(self, organization_id: UUID) -> tuple[WorkItem, ...]:
        rows = (
            await self._session.scalars(
                select(WorkItemRow).where(WorkItemRow.organization_id == organization_id)
            )
        ).all()
        return tuple(self._work_item(row) for row in rows)

    async def list_audits(self, organization_id: UUID) -> tuple[dict[str, object], ...]:
        rows = (
            await self._session.scalars(
                select(AuditRow)
                .where(AuditRow.organization_id == organization_id)
                .order_by(AuditRow.id.desc())
                .limit(100)
            )
        ).all()
        return tuple(
            {
                "id": row.id,
                "actor_subject": row.actor_subject,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": str(row.target_id),
                "correlation_id": str(row.correlation_id),
                "details": row.details,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        )

    async def add_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        correlation_id: UUID,
        details: dict[str, object],
    ) -> None:
        self._session.add(
            AuditRow(
                organization_id=organization_id,
                actor_subject=actor_subject,
                action=action,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id,
                details=details,
            )
        )

    async def add_outbox(self, event: EventEnvelope) -> None:
        self._session.add(
            OutboxRow(
                id=event.id,
                organization_id=event.organization_id,
                event_type=event.type,
                payload=event.model_dump(mode="json"),
            )
        )
        self._session.add(
            OutboxRoutingRow(event_id=event.id, organization_id=event.organization_id)
        )

    @staticmethod
    def _project(row: ProjectRow) -> Project:
        return Project(
            id=row.id,
            organization_id=row.organization_id,
            name=row.name,
            description=row.description,
            execution_approval_required=row.execution_approval_required,
            created_at=row.created_at,
        )

    @staticmethod
    def _intake_row(intake: IntakeRequest) -> IntakeRow:
        return IntakeRow(
            id=intake.id,
            organization_id=intake.organization_id,
            project_id=intake.project_id,
            client_id=intake.client_id,
            submitted_by=intake.submitted_by,
            problem=intake.problem,
            intended_users=intake.intended_users,
            required_functionality=list(intake.required_functionality),
            exclusions=list(intake.exclusions),
            constraints=list(intake.constraints),
            status=intake.status.value,
            created_at=intake.created_at,
        )

    @staticmethod
    def _intake(row: IntakeRow) -> IntakeRequest:
        return IntakeRequest(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            client_id=row.client_id,
            submitted_by=row.submitted_by,
            problem=row.problem,
            intended_users=row.intended_users,
            required_functionality=tuple(row.required_functionality),
            exclusions=tuple(row.exclusions),
            constraints=tuple(row.constraints),
            status=IntakeStatus(row.status),
            created_at=row.created_at,
        )

    @staticmethod
    def _specification(row: SpecificationRow) -> Specification:
        return Specification(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            intake_id=row.intake_id,
            current_version_id=row.current_version_id,
            current_version=row.current_version,
            status=SpecificationStatus(row.status),
        )

    @staticmethod
    def _specification_version(row: SpecificationVersionRow) -> SpecificationVersion:
        return SpecificationVersion(
            id=row.id,
            specification_id=row.specification_id,
            version=row.version,
            title=row.title,
            problem=row.problem,
            intended_users=row.intended_users,
            requirements=tuple(row.requirements),
            exclusions=tuple(row.exclusions),
            constraints=tuple(row.constraints),
            created_by=row.created_by,
            created_at=row.created_at,
        )

    @staticmethod
    def _work_item_row(work_item: WorkItem) -> WorkItemRow:
        return WorkItemRow(
            id=work_item.id,
            organization_id=work_item.organization_id,
            project_id=work_item.project_id,
            specification_version_id=work_item.specification_version_id,
            title=work_item.title,
            description=work_item.description,
            acceptance_criteria=list(work_item.acceptance_criteria),
            status=work_item.status.value,
            repository_connection_id=work_item.repository_connection_id,
            provider_configuration_id=work_item.provider_configuration_id,
            runner_pool_id=work_item.runner_pool_id,
            budget=asdict(work_item.budget) if work_item.budget else None,
            version=work_item.version,
        )

    @staticmethod
    def _work_item(row: WorkItemRow) -> WorkItem:
        data = cast(dict[str, Any] | None, row.budget)
        budget = (
            Budget(
                max_duration_seconds=int(data["max_duration_seconds"]),
                max_attempts=int(data["max_attempts"]),
                max_turns=int(data["max_turns"]),
                max_cost_minor=int(data["max_cost_minor"]),
                currency=str(data["currency"]),
            )
            if data
            else None
        )
        return WorkItem(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            specification_version_id=row.specification_version_id,
            title=row.title,
            description=row.description,
            acceptance_criteria=tuple(row.acceptance_criteria),
            status=WorkItemStatus(row.status),
            repository_connection_id=row.repository_connection_id,
            provider_configuration_id=row.provider_configuration_id,
            runner_pool_id=row.runner_pool_id,
            budget=budget,
            version=row.version,
        )


class PostgresUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.repository: ControlPlaneRepository

    async def __aenter__(self) -> "PostgresUnitOfWork":
        self._session = self._session_factory()
        self.repository = PostgresControlPlaneRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc is not None:
                await self._session.rollback()
            await self._session.close()

    async def set_organization(self, organization_id: UUID) -> None:
        if self._session is None:
            raise RuntimeError("unit of work has not been entered")
        await self._session.execute(
            text("select set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work has not been entered")
        await self._session.commit()
