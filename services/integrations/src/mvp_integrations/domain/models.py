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


class WebhookMode(StrEnum):
    WEBHOOK = "WEBHOOK"
    POLLING = "POLLING"


class ConfigurationHealth(StrEnum):
    PENDING = "PENDING"
    HEALTHY = "HEALTHY"
    INVALID = "INVALID"
    DISABLED = "DISABLED"


class RepositoryAccessStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class SourceControlConfiguration:
    id: UUID
    display_name: str
    provider: str
    web_base_url: str
    api_base_url: str
    api_version: str
    app_id: str
    client_id: str
    app_slug: str
    private_key_reference: dict[str, str | None]
    client_secret_reference: dict[str, str | None]
    webhook_secret_reference: dict[str, str | None]
    webhook_mode: WebhookMode
    enabled: bool
    health: ConfigurationHealth = ConfigurationHealth.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ConnectorInstallation:
    id: UUID
    organization_id: UUID
    provider: str
    external_account_id: str
    account_login: str
    requested_permissions: tuple[str, ...]
    is_development_substitute: bool
    provider_configuration_id: UUID | None = None
    granted_permissions: tuple[str, ...] = ()
    repository_selection: str = "SELECTED"
    last_reconciled_at: datetime | None = None
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
    access_status: RepositoryAccessStatus = RepositoryAccessStatus.ACTIVE
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
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
