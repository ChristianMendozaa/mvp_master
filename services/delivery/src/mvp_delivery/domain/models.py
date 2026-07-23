from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from mvp_common.contracts import ExternalReference, SecretReference

from mvp_delivery.domain.errors import BudgetExceeded, InvalidExecutionTransition


class AuthenticationMode(StrEnum):
    NONE = "NONE"
    LOCAL_SESSION = "LOCAL_SESSION"
    API_KEY_REFERENCE = "API_KEY_REFERENCE"
    ENTERPRISE_CONFIGURATION = "ENTERPRISE_CONFIGURATION"


class ExecutionStatus(StrEnum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    PLANNING = "PLANNING"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    BUILDING = "BUILDING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    AWAITING_HUMAN = "AWAITING_HUMAN"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RunnerStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DRAINING = "DRAINING"
    REVOKED = "REVOKED"


class ExecutionEventKind(StrEnum):
    DECISION = "DECISION"
    PLAN = "PLAN"
    TOOL = "TOOL"
    COMMAND = "COMMAND"
    RESULT = "RESULT"
    ERROR = "ERROR"
    APPROVAL = "APPROVAL"
    COST = "COST"
    STATE = "STATE"


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    max_duration_seconds: int
    max_attempts: int
    max_turns: int
    max_cost_minor: int
    currency: str = "USD"

    def ensure_within(
        self,
        *,
        duration_seconds: int,
        attempts: int,
        turns: int,
        cost_minor: int,
    ) -> None:
        exceeded: list[str] = []
        if duration_seconds > self.max_duration_seconds:
            exceeded.append("duration")
        if attempts > self.max_attempts:
            exceeded.append("attempts")
        if turns > self.max_turns:
            exceeded.append("turns")
        if cost_minor > self.max_cost_minor:
            exceeded.append("cost")
        if exceeded:
            raise BudgetExceeded(f"execution exceeded: {', '.join(exceeded)}")


@dataclass(frozen=True, slots=True)
class AgentProviderConfiguration:
    id: UUID
    organization_id: UUID
    display_name: str
    provider: str
    runtime: str
    model: str
    authentication_mode: AuthenticationMode
    secret_reference: SecretReference | None
    enabled: bool
    is_development_substitute: bool

    def __post_init__(self) -> None:
        needs_secret = self.authentication_mode is AuthenticationMode.API_KEY_REFERENCE
        if needs_secret != (self.secret_reference is not None):
            raise ValueError("API key mode requires exactly one secret reference")


@dataclass(slots=True)
class Runner:
    id: UUID
    organization_id: UUID
    pool_id: UUID
    name: str
    capabilities: tuple[str, ...]
    credential_hash: str
    status: RunnerStatus = RunnerStatus.ONLINE
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def heartbeat(self, capabilities: tuple[str, ...]) -> None:
        if self.status is RunnerStatus.REVOKED:
            raise InvalidExecutionTransition("a revoked runner cannot heartbeat")
        self.capabilities = capabilities
        self.last_seen_at = datetime.now(UTC)
        if self.status is RunnerStatus.OFFLINE:
            self.status = RunnerStatus.ONLINE


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    id: UUID
    execution_id: UUID
    organization_id: UUID
    sequence: int
    kind: ExecutionEventKind
    name: str
    message: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class Execution:
    id: UUID
    organization_id: UUID
    project_id: UUID
    work_item_id: UUID
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    repository_connection_id: UUID
    provider_configuration_id: UUID
    runner_pool_id: UUID
    budget: ExecutionBudget
    approval_status: ApprovalStatus
    status: ExecutionStatus = ExecutionStatus.AWAITING_APPROVAL
    attempt_count: int = 0
    turn_count: int = 0
    duration_seconds: int = 0
    cost_minor: int = 0
    version: int = 1
    cancellation_requested: bool = False
    result_reference: ExternalReference | None = None

    def approve(self) -> None:
        if self.status is not ExecutionStatus.AWAITING_APPROVAL:
            raise InvalidExecutionTransition(f"cannot approve execution from {self.status}")
        self.approval_status = ApprovalStatus.APPROVED
        self.status = ExecutionStatus.QUEUED
        self.version += 1

    def start_provisioning(self) -> None:
        self._transition(ExecutionStatus.QUEUED, ExecutionStatus.PROVISIONING)

    def start_planning(self) -> None:
        self._transition(ExecutionStatus.PROVISIONING, ExecutionStatus.PLANNING)

    def start_building(self) -> None:
        if self.status not in {ExecutionStatus.PLANNING, ExecutionStatus.REPAIRING}:
            raise InvalidExecutionTransition(f"cannot start building from {self.status}")
        self.status = ExecutionStatus.BUILDING
        self.version += 1

    def start_verification(self) -> None:
        self._transition(ExecutionStatus.BUILDING, ExecutionStatus.VERIFYING)

    def request_repair(self) -> None:
        if self.status is not ExecutionStatus.VERIFYING:
            raise InvalidExecutionTransition(f"cannot repair from {self.status}")
        if self.attempt_count >= self.budget.max_attempts:
            self.status = ExecutionStatus.AWAITING_HUMAN
        else:
            self.status = ExecutionStatus.REPAIRING
        self.version += 1

    def start_delivery(self) -> None:
        self._transition(ExecutionStatus.VERIFYING, ExecutionStatus.DELIVERING)

    def deliver(self, reference: ExternalReference) -> None:
        if self.status is not ExecutionStatus.DELIVERING:
            raise InvalidExecutionTransition(f"cannot deliver from {self.status}")
        self.result_reference = reference
        self.status = ExecutionStatus.DELIVERED
        self.version += 1

    def record_usage(
        self,
        *,
        attempts: int = 0,
        turns: int = 0,
        duration_seconds: int = 0,
        cost_minor: int = 0,
    ) -> None:
        next_attempts = self.attempt_count + attempts
        next_turns = self.turn_count + turns
        next_duration = self.duration_seconds + duration_seconds
        next_cost = self.cost_minor + cost_minor
        self.budget.ensure_within(
            duration_seconds=next_duration,
            attempts=next_attempts,
            turns=next_turns,
            cost_minor=next_cost,
        )
        self.attempt_count = next_attempts
        self.turn_count = next_turns
        self.duration_seconds = next_duration
        self.cost_minor = next_cost
        self.version += 1

    def request_cancellation(self) -> None:
        if self.status in {
            ExecutionStatus.DELIVERED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }:
            raise InvalidExecutionTransition(f"cannot cancel execution from {self.status}")
        self.cancellation_requested = True
        self.version += 1

    def cancel(self) -> None:
        if not self.cancellation_requested:
            raise InvalidExecutionTransition("cancellation has not been requested")
        self.status = ExecutionStatus.CANCELLED
        self.version += 1

    def fail(self) -> None:
        if self.status in {ExecutionStatus.DELIVERED, ExecutionStatus.CANCELLED}:
            raise InvalidExecutionTransition(f"cannot fail execution from {self.status}")
        self.status = ExecutionStatus.FAILED
        self.version += 1

    def _transition(self, expected: ExecutionStatus, target: ExecutionStatus) -> None:
        if self.status is not expected:
            raise InvalidExecutionTransition(f"cannot transition from {self.status} to {target}")
        self.status = target
        self.version += 1
