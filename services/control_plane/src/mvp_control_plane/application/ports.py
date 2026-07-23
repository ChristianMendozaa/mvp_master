from types import TracebackType
from typing import Protocol
from uuid import UUID

from mvp_common.contracts import EventEnvelope

from mvp_control_plane.domain.models import (
    Approval,
    IntakeRequest,
    Organization,
    Project,
    Role,
    Specification,
    SpecificationVersion,
    WorkItem,
)


class ControlPlaneRepository(Protocol):
    async def role_for(self, organization_id: UUID, subject: str) -> Role | None: ...

    async def add_organization(self, organization: Organization, owner_subject: str) -> None: ...

    async def list_organizations_for_subject(
        self, subject: str
    ) -> tuple[tuple[Organization, Role], ...]: ...

    async def add_project(self, project: Project) -> None: ...

    async def get_project(self, organization_id: UUID, project_id: UUID) -> Project | None: ...

    async def list_projects(self, organization_id: UUID) -> tuple[Project, ...]: ...

    async def add_intake(self, intake: IntakeRequest) -> None: ...

    async def get_intake(self, organization_id: UUID, intake_id: UUID) -> IntakeRequest | None: ...

    async def update_intake(self, intake: IntakeRequest) -> None: ...

    async def list_intakes(self, organization_id: UUID) -> tuple[IntakeRequest, ...]: ...

    async def add_specification(
        self, specification: Specification, version: SpecificationVersion
    ) -> None: ...

    async def get_specification(
        self, organization_id: UUID, specification_id: UUID
    ) -> Specification | None: ...

    async def get_specification_version(
        self, organization_id: UUID, version_id: UUID
    ) -> SpecificationVersion | None: ...

    async def update_specification(self, specification: Specification) -> None: ...

    async def list_specifications(self, organization_id: UUID) -> tuple[Specification, ...]: ...

    async def add_approval(self, approval: Approval) -> None: ...

    async def add_work_item(self, work_item: WorkItem) -> None: ...

    async def get_work_item(self, organization_id: UUID, work_item_id: UUID) -> WorkItem | None: ...

    async def update_work_item(self, work_item: WorkItem) -> None: ...

    async def list_work_items(self, organization_id: UUID) -> tuple[WorkItem, ...]: ...

    async def list_audits(self, organization_id: UUID) -> tuple[dict[str, object], ...]: ...

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
    ) -> None: ...

    async def add_outbox(self, event: EventEnvelope) -> None: ...


class UnitOfWork(Protocol):
    repository: ControlPlaneRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def set_organization(self, organization_id: UUID) -> None: ...

    async def commit(self) -> None: ...
