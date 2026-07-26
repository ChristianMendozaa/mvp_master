from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from mvp_common.contracts import SecretReference


class AgentEventKind(StrEnum):
    PLAN = "PLAN"
    TOOL = "TOOL"
    COMMAND = "COMMAND"
    RESULT = "RESULT"
    ERROR = "ERROR"
    APPROVAL = "APPROVAL"
    USAGE = "USAGE"


@dataclass(frozen=True, slots=True)
class AgentCapabilities:
    supports_resume: bool
    supports_structured_events: bool
    supports_usage: bool
    supports_approval: bool
    supported_authentication_modes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentRequest:
    execution_id: UUID
    organization_id: UUID
    provider: str
    model: str
    authentication_mode: str
    secret_reference: SecretReference | None
    workspace: PurePosixPath
    title: str
    problem: str
    acceptance_criteria: tuple[str, ...]
    max_turns: int
    max_duration_seconds: int


@dataclass(frozen=True, slots=True)
class AgentEvent:
    sequence: int
    kind: AgentEventKind
    name: str
    message: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentResult:
    success: bool
    summary: str
    session_id: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    turns: int
    changed_paths: tuple[str, ...]
    events: tuple[AgentEvent, ...]


@dataclass(frozen=True, slots=True)
class ValidationCommand:
    executable: str
    arguments: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    executable: str
    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    validator_image: str
    evidence: tuple[ValidationEvidence, ...]
