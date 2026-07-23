from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from mvp_control_plane.domain.errors import InvalidTransition


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    REVIEWER = "REVIEWER"
    CLIENT = "CLIENT"


class IntakeStatus(StrEnum):
    RECEIVED = "INTAKE_RECEIVED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SPECIFICATION_DRAFTED = "SPECIFICATION_DRAFTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SPECIFICATION_APPROVED = "SPECIFICATION_APPROVED"


class SpecificationStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class WorkItemStatus(StrEnum):
    IN_REVIEW = "WORK_ITEMS_GENERATED"
    REVIEWED = "WORK_ITEMS_REVIEWED"
    READY = "READY_FOR_EXECUTION"
    BUILDING = "BUILDING"
    VERIFICATION = "VERIFICATION"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    AWAITING_HUMAN = "AWAITING_HUMAN"


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class Project:
    id: UUID
    organization_id: UUID
    name: str
    description: str
    execution_approval_required: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class IntakeRequest:
    id: UUID
    organization_id: UUID
    project_id: UUID
    client_id: UUID | None
    submitted_by: str
    problem: str
    intended_users: str
    required_functionality: tuple[str, ...]
    exclusions: tuple[str, ...]
    constraints: tuple[str, ...]
    status: IntakeStatus = IntakeStatus.RECEIVED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_specification_drafted(self) -> None:
        if self.status not in {IntakeStatus.RECEIVED, IntakeStatus.CLARIFICATION_REQUIRED}:
            raise InvalidTransition(f"cannot draft specification from {self.status}")
        self.status = IntakeStatus.SPECIFICATION_DRAFTED

    def mark_awaiting_approval(self) -> None:
        if self.status is not IntakeStatus.SPECIFICATION_DRAFTED:
            raise InvalidTransition(f"cannot request approval from {self.status}")
        self.status = IntakeStatus.AWAITING_APPROVAL

    def mark_approved(self) -> None:
        if self.status is not IntakeStatus.AWAITING_APPROVAL:
            raise InvalidTransition(f"cannot approve intake from {self.status}")
        self.status = IntakeStatus.SPECIFICATION_APPROVED


@dataclass(frozen=True, slots=True)
class SpecificationVersion:
    id: UUID
    specification_id: UUID
    version: int
    title: str
    problem: str
    intended_users: str
    requirements: tuple[str, ...]
    exclusions: tuple[str, ...]
    constraints: tuple[str, ...]
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Specification:
    id: UUID
    organization_id: UUID
    project_id: UUID
    intake_id: UUID
    current_version_id: UUID
    current_version: int
    status: SpecificationStatus = SpecificationStatus.DRAFT

    def submit_for_approval(self) -> None:
        if self.status is not SpecificationStatus.DRAFT:
            raise InvalidTransition(f"cannot submit specification from {self.status}")
        self.status = SpecificationStatus.AWAITING_APPROVAL

    def approve(self) -> None:
        if self.status is not SpecificationStatus.AWAITING_APPROVAL:
            raise InvalidTransition(f"cannot approve specification from {self.status}")
        self.status = SpecificationStatus.APPROVED


@dataclass(frozen=True, slots=True)
class Approval:
    id: UUID
    organization_id: UUID
    subject_type: str
    subject_id: UUID
    subject_version: int
    decision: str
    actor_subject: str
    reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class Budget:
    max_duration_seconds: int
    max_attempts: int
    max_turns: int
    max_cost_minor: int
    currency: str = "USD"

    def __post_init__(self) -> None:
        if min(self.max_duration_seconds, self.max_attempts, self.max_turns) < 1:
            raise ValueError("duration, attempts and turns must be positive")
        if self.max_cost_minor < 0:
            raise ValueError("cost cannot be negative")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be a three-letter uppercase code")


@dataclass(slots=True)
class WorkItem:
    id: UUID
    organization_id: UUID
    project_id: UUID
    specification_version_id: UUID
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    status: WorkItemStatus = WorkItemStatus.IN_REVIEW
    repository_connection_id: UUID | None = None
    provider_configuration_id: UUID | None = None
    runner_pool_id: UUID | None = None
    budget: Budget | None = None
    version: int = 1

    def mark_reviewed(self) -> None:
        if self.status is not WorkItemStatus.IN_REVIEW:
            raise InvalidTransition(f"cannot review work item from {self.status}")
        self.status = WorkItemStatus.REVIEWED
        self.version += 1

    def mark_ready(
        self,
        *,
        repository_connection_id: UUID,
        provider_configuration_id: UUID,
        runner_pool_id: UUID,
        budget: Budget,
    ) -> None:
        if self.status is not WorkItemStatus.REVIEWED:
            raise InvalidTransition(f"cannot ready work item from {self.status}")
        self.repository_connection_id = repository_connection_id
        self.provider_configuration_id = provider_configuration_id
        self.runner_pool_id = runner_pool_id
        self.budget = budget
        self.status = WorkItemStatus.READY
        self.version += 1
