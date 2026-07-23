from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from mvp_integrations.domain.models import (
    ConnectorInstallation,
    PullRequestResult,
    RepositoryConnection,
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


class IntegrationRepository(Protocol):
    async def add_installation(self, installation: ConnectorInstallation) -> None: ...

    async def get_installation(
        self, organization_id: UUID, installation_id: UUID
    ) -> ConnectorInstallation | None: ...

    async def organization_for_external_installation(
        self, provider: str, external_account_id: str
    ) -> UUID | None: ...

    async def update_installation(self, installation: ConnectorInstallation) -> None: ...

    async def add_repository(self, repository: RepositoryConnection) -> None: ...

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
