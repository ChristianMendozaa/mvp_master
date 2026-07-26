from uuid import uuid4

import pytest
from mvp_delivery.adapters.activities import AGENT_EVENT_KIND_MAP
from mvp_delivery.adapters.memory import MemoryDeliveryRepository, MemoryWorkflowGateway
from mvp_delivery.application.service import DeliveryService
from mvp_delivery.domain.agent_runtimes import RUNTIME_COMPATIBILITY, ensure_supported
from mvp_delivery.domain.errors import (
    BudgetExceeded,
    InvalidEnrollment,
    UnsupportedProviderConfiguration,
)
from mvp_delivery.domain.models import (
    AgentProviderConfiguration,
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


@pytest.mark.parametrize(
    ("runtime", "provider", "authentication_mode", "is_development_substitute"),
    [
        ("deterministic", "local", "NONE", True),
        ("codex-cli", "openai", "LOCAL_SESSION", False),
        ("codex-cli", "openai", "API_KEY_REFERENCE", False),
        ("claude-code-cli", "anthropic", "LOCAL_SESSION", False),
        ("claude-code-cli", "anthropic", "API_KEY_REFERENCE", False),
        ("claude-code-cli", "zhipu-glm", "API_KEY_REFERENCE", False),
        ("claude-code-cli", "moonshot-kimi", "API_KEY_REFERENCE", False),
        ("claude-agent-sdk", "anthropic", "API_KEY_REFERENCE", False),
    ],
)
def test_ensure_supported_accepts_every_valid_combination(
    runtime: str, provider: str, authentication_mode: str, is_development_substitute: bool
) -> None:
    ensure_supported(
        runtime=runtime,
        provider=provider,
        authentication_mode=authentication_mode,
        is_development_substitute=is_development_substitute,
    )


@pytest.mark.parametrize(
    ("runtime", "provider", "authentication_mode", "is_development_substitute"),
    [
        ("not-a-real-runtime", "local", "NONE", True),
        ("deterministic", "not-a-real-provider", "NONE", True),
        ("deterministic", "local", "API_KEY_REFERENCE", True),
        ("claude-agent-sdk", "anthropic", "LOCAL_SESSION", False),
        ("claude-code-cli", "zhipu-glm", "LOCAL_SESSION", False),
        ("claude-code-cli", "moonshot-kimi", "LOCAL_SESSION", False),
        ("codex-cli", "anthropic", "API_KEY_REFERENCE", False),
        ("deterministic", "local", "NONE", False),  # wrong is_development_substitute
    ],
)
def test_ensure_supported_rejects_every_invalid_combination(
    runtime: str, provider: str, authentication_mode: str, is_development_substitute: bool
) -> None:
    with pytest.raises(UnsupportedProviderConfiguration):
        ensure_supported(
            runtime=runtime,
            provider=provider,
            authentication_mode=authentication_mode,
            is_development_substitute=is_development_substitute,
        )


def test_agent_provider_configuration_rejects_unsupported_combination() -> None:
    with pytest.raises(UnsupportedProviderConfiguration):
        AgentProviderConfiguration(
            id=uuid4(),
            organization_id=uuid4(),
            display_name="Bad config",
            provider="anthropic",
            runtime="claude-agent-sdk",
            model="claude-opus-5",
            authentication_mode=AuthenticationMode.LOCAL_SESSION,
            secret_reference=None,
            enabled=True,
            is_development_substitute=False,
        )


def test_agent_event_kind_map_covers_every_kind_the_wire_contract_allows() -> None:
    """Keeps `activities.py`'s AGENT_EVENT_KIND_MAP in sync with the
    `AgentEventReport.kind` pattern in `entrypoints/api.py` forever: every kind the
    HTTP layer accepts from a runner must have a mapping to an `ExecutionEventKind`,
    or a legitimate USAGE-reporting adapter would silently degrade to TOOL."""
    wire_kinds = {"PLAN", "TOOL", "COMMAND", "RESULT", "ERROR", "APPROVAL", "USAGE"}
    assert set(AGENT_EVENT_KIND_MAP) == wire_kinds


def test_runtime_compatibility_table_matches_the_runner_registry() -> None:
    """The runtimes named here must be exactly the ones the runner's own registry
    knows about (`agent_registry.SUPPORTED_RUNTIMES`) — kept as a literal set here,
    since delivery must not import runner code, to catch the two drifting apart."""
    assert set(RUNTIME_COMPATIBILITY) == {
        "deterministic",
        "codex-cli",
        "claude-code-cli",
        "claude-agent-sdk",
    }
