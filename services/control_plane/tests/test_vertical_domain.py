from uuid import UUID, uuid4

import pytest
from mvp_control_plane.adapters.memory import MemoryControlPlaneRepository, MemoryUnitOfWork
from mvp_control_plane.application.service import ControlPlaneService
from mvp_control_plane.domain.errors import PermissionDenied
from mvp_control_plane.domain.models import Budget, Role, WorkItemStatus


async def build_approved_work_item(
    repository: MemoryControlPlaneRepository,
    *,
    owner: str = "owner@example.test",
) -> tuple[ControlPlaneService, UUID, UUID]:
    service = ControlPlaneService(MemoryUnitOfWork(repository))
    correlation_id = uuid4()
    organization = await service.create_organization(
        actor_subject=owner, name="Acme", correlation_id=correlation_id
    )
    project = await service.create_project(
        actor_subject=owner,
        organization_id=organization.id,
        name="Portal",
        description="Client portal",
        correlation_id=correlation_id,
    )
    intake = await service.submit_intake(
        actor_subject=owner,
        organization_id=organization.id,
        project_id=project.id,
        client_id=None,
        problem="Clients cannot see delivery status.",
        intended_users="Client stakeholders",
        required_functionality=("Show a delivery status card",),
        exclusions=("No mobile application",),
        constraints=("Accessible at WCAG 2.2 AA",),
        correlation_id=correlation_id,
    )
    specification, _ = await service.draft_specification(
        actor_subject=owner,
        organization_id=organization.id,
        intake_id=intake.id,
        title="Delivery status card",
        correlation_id=correlation_id,
    )
    await service.submit_specification(
        actor_subject=owner,
        organization_id=organization.id,
        specification_id=specification.id,
        correlation_id=correlation_id,
    )
    _, work_item = await service.approve_specification(
        actor_subject=owner,
        organization_id=organization.id,
        specification_id=specification.id,
        reason="Scope is clear",
        correlation_id=correlation_id,
    )
    return service, organization.id, work_item.id


async def test_approved_work_item_emits_versioned_ready_event() -> None:
    repository = MemoryControlPlaneRepository()
    service, organization_id, work_item_id = await build_approved_work_item(repository)
    await service.review_work_item(
        actor_subject="owner@example.test",
        organization_id=organization_id,
        work_item_id=work_item_id,
        correlation_id=uuid4(),
    )
    ready = await service.ready_work_item(
        actor_subject="owner@example.test",
        organization_id=organization_id,
        work_item_id=work_item_id,
        repository_connection_id=uuid4(),
        provider_configuration_id=uuid4(),
        runner_pool_id=uuid4(),
        budget=Budget(
            max_duration_seconds=600,
            max_attempts=2,
            max_turns=8,
            max_cost_minor=500,
        ),
        correlation_id=uuid4(),
    )

    assert ready.status is WorkItemStatus.READY
    assert repository.outbox[-1].type == "com.mvp.work_item.ready.v1"
    assert repository.outbox[-1].organization_id == organization_id
    assert any(audit["action"] == "work_item.readied" for audit in repository.audits)


async def test_client_cannot_approve_specification() -> None:
    repository = MemoryControlPlaneRepository()
    service, organization_id, work_item_id = await build_approved_work_item(repository)
    repository.memberships[(organization_id, "client@example.test")] = Role.CLIENT

    with pytest.raises(PermissionDenied):
        await service.review_work_item(
            actor_subject="client@example.test",
            organization_id=organization_id,
            work_item_id=work_item_id,
            correlation_id=uuid4(),
        )
