from uuid import uuid4

import pytest
from mvp_delivery.adapters.memory import MemoryDeliveryRepository, MemoryWorkflowGateway
from mvp_delivery.application.service import DeliveryService
from mvp_delivery.domain.errors import BudgetExceeded, InvalidEnrollment
from mvp_delivery.domain.models import (
    AuthenticationMode,
    ExecutionBudget,
    ExecutionStatus,
)


async def test_enrollment_is_single_use_and_stores_only_hash() -> None:
    repository = MemoryDeliveryRepository()
    service = DeliveryService(repository, MemoryWorkflowGateway())
    token = await service.create_runner_enrollment(
        organization_id=uuid4(),
        actor_subject="owner@example.test",
        pool_id=uuid4(),
    )
    runner, credential = await service.enroll_runner(
        enrollment_token=token,
        name="local-runner",
        capabilities=("docker", "deterministic"),
    )
    assert token not in {record.token_hash for record in repository.enrollment_tokens.values()}
    assert credential != runner.credential_hash
    with pytest.raises(InvalidEnrollment):
        await service.enroll_runner(
            enrollment_token=token,
            name="duplicate",
            capabilities=("docker",),
        )


async def test_ready_event_is_idempotent_and_waits_for_approval() -> None:
    repository = MemoryDeliveryRepository()
    workflows = MemoryWorkflowGateway()
    service = DeliveryService(repository, workflows)
    organization_id = uuid4()
    configuration = await service.create_provider_configuration(
        organization_id=organization_id,
        actor_subject="owner@example.test",
        display_name="Deterministic local agent",
        provider="local",
        runtime="deterministic",
        model="deterministic-v1",
        authentication_mode=AuthenticationMode.NONE,
        secret_reference=None,
        is_development_substitute=True,
    )
    kwargs = {
        "organization_id": organization_id,
        "project_id": uuid4(),
        "work_item_id": uuid4(),
        "title": "Delivery status",
        "description": "Make the current delivery state clear.",
        "acceptance_criteria": ("A status card is visible.",),
        "repository_connection_id": uuid4(),
        "provider_configuration_id": configuration.id,
        "runner_pool_id": uuid4(),
        "budget": ExecutionBudget(600, 2, 8, 500),
        "correlation_id": uuid4(),
    }
    first = await service.accept_ready_work_item(**kwargs)
    second = await service.accept_ready_work_item(**kwargs)
    assert first.id == second.id
    assert first.status is ExecutionStatus.AWAITING_APPROVAL
    assert workflows.started == [first.id]

    approved = await service.approve_execution(
        organization_id=organization_id,
        execution_id=first.id,
        actor_subject="reviewer@example.test",
    )
    assert approved.status is ExecutionStatus.QUEUED
    assert workflows.approved == [(first.id, "reviewer@example.test")]


def test_budget_fails_before_recording_excess_usage() -> None:
    budget = ExecutionBudget(60, 1, 2, 100)
    budget.ensure_within(duration_seconds=60, attempts=1, turns=2, cost_minor=100)
    with pytest.raises(BudgetExceeded):
        budget.ensure_within(duration_seconds=61, attempts=1, turns=2, cost_minor=100)
