from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mvp_common.contracts import SecretReference

from mvp_integrations.domain.models import (
    ConnectorInstallation,
    PullRequestResult,
    RepositoryConnection,
    SourceControlConfiguration,
)


@dataclass(frozen=True, slots=True)
class RepositoryDescriptor:
    external_id: str
    owner: str
    name: str
    default_branch: str
    clone_locator: str
    is_private: bool


class SourceControlProvider(Protocol):
    provider_name: str
    is_development_substitute: bool

    async def repositories(self, external_account_id: str) -> tuple[RepositoryDescriptor, ...]: ...

    async def create_pull_request(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        idempotency_key: str,
    ) -> PullRequestResult: ...

    async def add_comment(
        self,
        *,
        installation: ConnectorInstallation,
        external_reference_id: str,
        body: str,
        idempotency_key: str,
    ) -> None: ...

    async def create_check_run(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        head_sha: str,
        name: str,
        summary: str,
        idempotency_key: str,
    ) -> None: ...


class SecretStore(Protocol):
    async def put(self, reference: SecretReference, value: bytes) -> None: ...

    async def get(self, reference: SecretReference) -> bytes: ...

    async def delete(self, reference: SecretReference) -> None: ...


class IntegrationRepository(Protocol):
    async def create_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, expires_at: datetime
    ) -> None: ...

    async def consume_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, now: datetime
    ) -> bool: ...

    async def create_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        configuration_id: UUID,
        expires_at: datetime,
    ) -> None: ...

    async def consume_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        now: datetime,
    ) -> UUID | None: ...

    async def redeem_source_capability(
        self,
        organization_id: UUID,
        capability_id: str,
        expires_at: datetime,
    ) -> bool: ...

    async def add_source_control_configuration(
        self, configuration: SourceControlConfiguration
    ) -> None: ...

    async def get_source_control_configuration(
        self, configuration_id: UUID
    ) -> SourceControlConfiguration | None: ...

    async def source_control_configuration_for_app_id(
        self, provider: str, app_id: str
    ) -> SourceControlConfiguration | None: ...

    async def list_source_control_configurations(
        self,
    ) -> tuple[SourceControlConfiguration, ...]: ...

    async def update_source_control_configuration_health(
        self, configuration_id: UUID, health: str, enabled: bool
    ) -> None: ...

    async def record_platform_audit(
        self,
        *,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None: ...

    async def add_installation(self, installation: ConnectorInstallation) -> None: ...

    async def get_installation(
        self, organization_id: UUID, installation_id: UUID
    ) -> ConnectorInstallation | None: ...

    async def organization_for_external_installation(
        self, provider: str, external_account_id: str
    ) -> UUID | None: ...

    async def installation_for_external(
        self, organization_id: UUID, provider: str, external_account_id: str
    ) -> ConnectorInstallation | None: ...

    async def list_installation_routes(self) -> tuple[tuple[UUID, UUID], ...]: ...

    async def update_installation(self, installation: ConnectorInstallation) -> None: ...

    async def add_repository(self, repository: RepositoryConnection) -> None: ...

    async def upsert_repository(self, repository: RepositoryConnection) -> None: ...

    async def revoke_repositories_except(
        self,
        organization_id: UUID,
        installation_id: UUID,
        active_external_ids: set[str],
        revoked_at: datetime,
    ) -> None: ...

    async def get_repository(
        self, organization_id: UUID, repository_id: UUID
    ) -> RepositoryConnection | None: ...

    async def list_repositories(
        self, organization_id: UUID
    ) -> tuple[RepositoryConnection, ...]: ...

    async def record_webhook_delivery(
        self,
        *,
        provider: str,
        delivery_id: str,
        organization_id: UUID | None,
        event_name: str,
        payload_hash: str,
    ) -> bool: ...

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None: ...
