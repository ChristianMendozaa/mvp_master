from types import TracebackType
from uuid import UUID

from mvp_common.contracts import EventEnvelope

from mvp_control_plane.application.ports import ControlPlaneRepository
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


class MemoryControlPlaneRepository(ControlPlaneRepository):
    def __init__(self) -> None:
        self.organizations: dict[UUID, Organization] = {}
        self.memberships: dict[tuple[UUID, str], Role] = {}
        self.projects: dict[UUID, Project] = {}
        self.intakes: dict[UUID, IntakeRequest] = {}
        self.specifications: dict[UUID, Specification] = {}
        self.specification_versions: dict[UUID, SpecificationVersion] = {}
        self.approvals: dict[UUID, Approval] = {}
        self.work_items: dict[UUID, WorkItem] = {}
        self.audits: list[dict[str, object]] = []
        self.outbox: list[EventEnvelope] = []

    async def role_for(self, organization_id: UUID, subject: str) -> Role | None:
        return self.memberships.get((organization_id, subject))

    async def add_organization(self, organization: Organization, owner_subject: str) -> None:
        self.organizations[organization.id] = organization
        self.memberships[(organization.id, owner_subject)] = Role.OWNER

    async def list_organizations_for_subject(
        self, subject: str
    ) -> tuple[tuple[Organization, Role], ...]:
        return tuple(
            (self.organizations[organization_id], role)
            for (organization_id, member_subject), role in self.memberships.items()
            if member_subject == subject
        )

    async def add_project(self, project: Project) -> None:
        self.projects[project.id] = project

    async def get_project(self, organization_id: UUID, project_id: UUID) -> Project | None:
        project = self.projects.get(project_id)
        return project if project and project.organization_id == organization_id else None

    async def list_projects(self, organization_id: UUID) -> tuple[Project, ...]:
        return tuple(
            item for item in self.projects.values() if item.organization_id == organization_id
        )

    async def add_intake(self, intake: IntakeRequest) -> None:
        self.intakes[intake.id] = intake

    async def get_intake(self, organization_id: UUID, intake_id: UUID) -> IntakeRequest | None:
        intake = self.intakes.get(intake_id)
        return intake if intake and intake.organization_id == organization_id else None

    async def update_intake(self, intake: IntakeRequest) -> None:
        self.intakes[intake.id] = intake

    async def list_intakes(self, organization_id: UUID) -> tuple[IntakeRequest, ...]:
        return tuple(
            item for item in self.intakes.values() if item.organization_id == organization_id
        )

    async def add_specification(
        self, specification: Specification, version: SpecificationVersion
    ) -> None:
        self.specifications[specification.id] = specification
        self.specification_versions[version.id] = version

    async def get_specification(
        self, organization_id: UUID, specification_id: UUID
    ) -> Specification | None:
        specification = self.specifications.get(specification_id)
        return (
            specification
            if specification and specification.organization_id == organization_id
            else None
        )

    async def get_specification_version(
        self, organization_id: UUID, version_id: UUID
    ) -> SpecificationVersion | None:
        version = self.specification_versions.get(version_id)
        if version is None:
            return None
        specification = self.specifications.get(version.specification_id)
        if specification is None or specification.organization_id != organization_id:
            return None
        return version

    async def update_specification(self, specification: Specification) -> None:
        self.specifications[specification.id] = specification

    async def list_specifications(self, organization_id: UUID) -> tuple[Specification, ...]:
        return tuple(
            item for item in self.specifications.values() if item.organization_id == organization_id
        )

    async def add_approval(self, approval: Approval) -> None:
        self.approvals[approval.id] = approval

    async def add_work_item(self, work_item: WorkItem) -> None:
        self.work_items[work_item.id] = work_item

    async def get_work_item(self, organization_id: UUID, work_item_id: UUID) -> WorkItem | None:
        work_item = self.work_items.get(work_item_id)
        return work_item if work_item and work_item.organization_id == organization_id else None

    async def update_work_item(self, work_item: WorkItem) -> None:
        self.work_items[work_item.id] = work_item

    async def list_work_items(self, organization_id: UUID) -> tuple[WorkItem, ...]:
        return tuple(
            item for item in self.work_items.values() if item.organization_id == organization_id
        )

    async def list_audits(self, organization_id: UUID) -> tuple[dict[str, object], ...]:
        return tuple(item for item in self.audits if item["organization_id"] == organization_id)

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
        self.audits.append(
            {
                "organization_id": organization_id,
                "actor_subject": actor_subject,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "correlation_id": correlation_id,
                "details": details,
            }
        )

    async def add_outbox(self, event: EventEnvelope) -> None:
        self.outbox.append(event)


class MemoryUnitOfWork:
    def __init__(self, repository: MemoryControlPlaneRepository | None = None) -> None:
        self.repository = repository or MemoryControlPlaneRepository()
        self.organization_id: UUID | None = None
        self.committed = False

    async def __aenter__(self) -> "MemoryUnitOfWork":
        self.committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def set_organization(self, organization_id: UUID) -> None:
        self.organization_id = organization_id

    async def commit(self) -> None:
        self.committed = True
