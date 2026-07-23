from dataclasses import asdict
from uuid import UUID, uuid4

from mvp_common.contracts import EventEnvelope

from mvp_control_plane.application.ports import UnitOfWork
from mvp_control_plane.domain.errors import NotFound
from mvp_control_plane.domain.models import (
    Approval,
    Budget,
    IntakeRequest,
    Organization,
    Project,
    Role,
    Specification,
    SpecificationVersion,
    WorkItem,
)
from mvp_control_plane.domain.permissions import (
    EXECUTION_REQUESTERS,
    INTAKE_CREATORS,
    PROJECT_EDITORS,
    REVIEWERS,
    require_role,
)


class ControlPlaneService:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._uow = unit_of_work

    async def create_organization(
        self, *, actor_subject: str, name: str, correlation_id: UUID
    ) -> Organization:
        organization = Organization(id=uuid4(), name=name.strip())
        async with self._uow:
            await self._uow.set_organization(organization.id)
            await self._uow.repository.add_organization(organization, actor_subject)
            await self._uow.repository.add_outbox(
                EventEnvelope(
                    id=uuid4(),
                    source="urn:mvp-master:control-plane",
                    type="com.mvp.membership.changed.v1",
                    subject=f"organization/{organization.id}/membership/{actor_subject}",
                    organization_id=organization.id,
                    aggregate_version=1,
                    correlation_id=correlation_id,
                    data={
                        "subject": actor_subject,
                        "role": "OWNER",
                        "active": True,
                        "project_ids": [],
                        "client_ids": [],
                    },
                )
            )
            await self._audit(
                organization.id,
                actor_subject,
                "organization.created",
                "organization",
                organization.id,
                correlation_id,
                {"name": organization.name},
            )
            await self._uow.commit()
        return organization

    async def organizations_for(
        self, *, actor_subject: str
    ) -> tuple[tuple[Organization, Role], ...]:
        async with self._uow:
            return await self._uow.repository.list_organizations_for_subject(actor_subject)

    async def dashboard(
        self, *, actor_subject: str, organization_id: UUID
    ) -> dict[str, tuple[object, ...]]:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                {
                    *PROJECT_EDITORS,
                    *REVIEWERS,
                },
            )
            return {
                "projects": await self._uow.repository.list_projects(organization_id),
                "intakes": await self._uow.repository.list_intakes(organization_id),
                "specifications": await self._uow.repository.list_specifications(organization_id),
                "work_items": await self._uow.repository.list_work_items(organization_id),
                "audits": await self._uow.repository.list_audits(organization_id),
            }

    async def create_project(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        name: str,
        description: str,
        correlation_id: UUID,
    ) -> Project:
        project = Project(
            id=uuid4(),
            organization_id=organization_id,
            name=name.strip(),
            description=description.strip(),
        )
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                PROJECT_EDITORS,
            )
            await self._uow.repository.add_project(project)
            await self._audit(
                organization_id,
                actor_subject,
                "project.created",
                "project",
                project.id,
                correlation_id,
                {"name": project.name},
            )
            await self._uow.commit()
        return project

    async def submit_intake(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        project_id: UUID,
        client_id: UUID | None,
        problem: str,
        intended_users: str,
        required_functionality: tuple[str, ...],
        exclusions: tuple[str, ...],
        constraints: tuple[str, ...],
        correlation_id: UUID,
    ) -> IntakeRequest:
        intake = IntakeRequest(
            id=uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            client_id=client_id,
            submitted_by=actor_subject,
            problem=problem.strip(),
            intended_users=intended_users.strip(),
            required_functionality=tuple(item.strip() for item in required_functionality),
            exclusions=tuple(item.strip() for item in exclusions),
            constraints=tuple(item.strip() for item in constraints),
        )
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                INTAKE_CREATORS,
            )
            if await self._uow.repository.get_project(organization_id, project_id) is None:
                raise NotFound("project not found")
            await self._uow.repository.add_intake(intake)
            await self._audit(
                organization_id,
                actor_subject,
                "intake.submitted",
                "intake",
                intake.id,
                correlation_id,
                {"project_id": str(project_id)},
            )
            await self._uow.commit()
        return intake

    async def draft_specification(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        intake_id: UUID,
        title: str,
        correlation_id: UUID,
    ) -> tuple[Specification, SpecificationVersion]:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                PROJECT_EDITORS | REVIEWERS,
            )
            intake = await self._uow.repository.get_intake(organization_id, intake_id)
            if intake is None:
                raise NotFound("intake not found")
            intake.mark_specification_drafted()
            specification_id = uuid4()
            version = SpecificationVersion(
                id=uuid4(),
                specification_id=specification_id,
                version=1,
                title=title.strip(),
                problem=intake.problem,
                intended_users=intake.intended_users,
                requirements=intake.required_functionality,
                exclusions=intake.exclusions,
                constraints=intake.constraints,
                created_by=actor_subject,
            )
            specification = Specification(
                id=specification_id,
                organization_id=organization_id,
                project_id=intake.project_id,
                intake_id=intake.id,
                current_version_id=version.id,
                current_version=version.version,
            )
            await self._uow.repository.update_intake(intake)
            await self._uow.repository.add_specification(specification, version)
            await self._audit(
                organization_id,
                actor_subject,
                "specification.drafted",
                "specification",
                specification.id,
                correlation_id,
                {"version": 1, "intake_id": str(intake.id)},
            )
            await self._uow.commit()
        return specification, version

    async def submit_specification(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        specification_id: UUID,
        correlation_id: UUID,
    ) -> Specification:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                PROJECT_EDITORS | REVIEWERS,
            )
            specification = await self._required_specification(organization_id, specification_id)
            intake = await self._required_intake(organization_id, specification.intake_id)
            specification.submit_for_approval()
            intake.mark_awaiting_approval()
            await self._uow.repository.update_specification(specification)
            await self._uow.repository.update_intake(intake)
            await self._audit(
                organization_id,
                actor_subject,
                "specification.submitted",
                "specification",
                specification.id,
                correlation_id,
                {"version": specification.current_version},
            )
            await self._uow.commit()
        return specification

    async def approve_specification(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        specification_id: UUID,
        reason: str | None,
        correlation_id: UUID,
    ) -> tuple[Specification, WorkItem]:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject), REVIEWERS
            )
            specification = await self._required_specification(organization_id, specification_id)
            version = await self._uow.repository.get_specification_version(
                organization_id, specification.current_version_id
            )
            if version is None:
                raise NotFound("specification version not found")
            intake = await self._required_intake(organization_id, specification.intake_id)
            specification.approve()
            intake.mark_approved()
            approval = Approval(
                id=uuid4(),
                organization_id=organization_id,
                subject_type="specification",
                subject_id=specification.id,
                subject_version=specification.current_version,
                decision="APPROVED",
                actor_subject=actor_subject,
                reason=reason,
            )
            work_item = WorkItem(
                id=uuid4(),
                organization_id=organization_id,
                project_id=specification.project_id,
                specification_version_id=version.id,
                title=version.title,
                description=version.problem,
                acceptance_criteria=version.requirements,
            )
            await self._uow.repository.update_specification(specification)
            await self._uow.repository.update_intake(intake)
            await self._uow.repository.add_approval(approval)
            await self._uow.repository.add_work_item(work_item)
            await self._audit(
                organization_id,
                actor_subject,
                "specification.approved",
                "specification",
                specification.id,
                correlation_id,
                {"version": specification.current_version, "work_item_id": str(work_item.id)},
            )
            await self._uow.commit()
        return specification, work_item

    async def review_work_item(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        work_item_id: UUID,
        correlation_id: UUID,
    ) -> WorkItem:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject), REVIEWERS
            )
            work_item = await self._required_work_item(organization_id, work_item_id)
            work_item.mark_reviewed()
            await self._uow.repository.update_work_item(work_item)
            await self._audit(
                organization_id,
                actor_subject,
                "work_item.reviewed",
                "work_item",
                work_item.id,
                correlation_id,
                {"version": work_item.version},
            )
            await self._uow.commit()
        return work_item

    async def ready_work_item(
        self,
        *,
        actor_subject: str,
        organization_id: UUID,
        work_item_id: UUID,
        repository_connection_id: UUID,
        provider_configuration_id: UUID,
        runner_pool_id: UUID,
        budget: Budget,
        correlation_id: UUID,
    ) -> WorkItem:
        async with self._uow:
            await self._uow.set_organization(organization_id)
            require_role(
                await self._uow.repository.role_for(organization_id, actor_subject),
                EXECUTION_REQUESTERS,
            )
            work_item = await self._required_work_item(organization_id, work_item_id)
            work_item.mark_ready(
                repository_connection_id=repository_connection_id,
                provider_configuration_id=provider_configuration_id,
                runner_pool_id=runner_pool_id,
                budget=budget,
            )
            await self._uow.repository.update_work_item(work_item)
            event_id = uuid4()
            await self._uow.repository.add_outbox(
                EventEnvelope(
                    id=event_id,
                    source="urn:mvp-master:control-plane",
                    type="com.mvp.work_item.ready.v1",
                    subject=f"work-item/{work_item.id}",
                    organization_id=organization_id,
                    aggregate_version=work_item.version,
                    correlation_id=correlation_id,
                    data={
                        "work_item_id": str(work_item.id),
                        "project_id": str(work_item.project_id),
                        "repository_connection_id": str(repository_connection_id),
                        "provider_configuration_id": str(provider_configuration_id),
                        "runner_pool_id": str(runner_pool_id),
                        "budget": asdict(budget),
                        "title": work_item.title,
                        "description": work_item.description,
                        "acceptance_criteria": list(work_item.acceptance_criteria),
                    },
                )
            )
            await self._audit(
                organization_id,
                actor_subject,
                "work_item.readied",
                "work_item",
                work_item.id,
                correlation_id,
                {"event_id": str(event_id), "version": work_item.version},
            )
            await self._uow.commit()
        return work_item

    async def _required_intake(self, organization_id: UUID, intake_id: UUID) -> IntakeRequest:
        intake = await self._uow.repository.get_intake(organization_id, intake_id)
        if intake is None:
            raise NotFound("intake not found")
        return intake

    async def _required_specification(
        self, organization_id: UUID, specification_id: UUID
    ) -> Specification:
        specification = await self._uow.repository.get_specification(
            organization_id, specification_id
        )
        if specification is None:
            raise NotFound("specification not found")
        return specification

    async def _required_work_item(self, organization_id: UUID, work_item_id: UUID) -> WorkItem:
        work_item = await self._uow.repository.get_work_item(organization_id, work_item_id)
        if work_item is None:
            raise NotFound("work item not found")
        return work_item

    async def _audit(
        self,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        correlation_id: UUID,
        details: dict[str, object],
    ) -> None:
        await self._uow.repository.add_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action=action,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            details=details,
        )
