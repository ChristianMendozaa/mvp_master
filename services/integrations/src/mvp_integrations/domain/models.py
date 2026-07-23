from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from mvp_common.contracts import ExternalReference

from mvp_integrations.domain.errors import InvalidInstallationState


class InstallationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISCONNECTED = "DISCONNECTED"


@dataclass(slots=True)
class ConnectorInstallation:
    id: UUID
    organization_id: UUID
    provider: str
    external_account_id: str
    account_login: str
    requested_permissions: tuple[str, ...]
    is_development_substitute: bool
    status: InstallationStatus = InstallationStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def suspend(self) -> None:
        if self.status is InstallationStatus.DISCONNECTED:
            raise InvalidInstallationState("a disconnected installation cannot be suspended")
        self.status = InstallationStatus.SUSPENDED

    def activate(self) -> None:
        if self.status is InstallationStatus.DISCONNECTED:
            raise InvalidInstallationState("a disconnected installation cannot be reactivated")
        self.status = InstallationStatus.ACTIVE

    def disconnect(self) -> None:
        self.status = InstallationStatus.DISCONNECTED


@dataclass(frozen=True, slots=True)
class RepositoryConnection:
    id: UUID
    organization_id: UUID
    installation_id: UUID
    external_repository_id: str
    owner: str
    name: str
    default_branch: str
    clone_locator: str
    is_private: bool
    is_development_substitute: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True, slots=True)
class PullRequestResult:
    reference: ExternalReference
    title: str
    url: str
    head_branch: str
    base_branch: str
    is_development_substitute: bool
