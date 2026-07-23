from uuid import UUID

from mvp_integrations.application.ports import IntegrationRepository
from mvp_integrations.domain.models import ConnectorInstallation, RepositoryConnection


class MemoryIntegrationRepository(IntegrationRepository):
    def __init__(self) -> None:
        self.installations: dict[UUID, ConnectorInstallation] = {}
        self.repositories: dict[UUID, RepositoryConnection] = {}
        self.webhook_deliveries: set[tuple[str, str]] = set()
        self.audits: list[dict[str, object]] = []

    async def add_installation(self, installation: ConnectorInstallation) -> None:
        self.installations[installation.id] = installation

    async def get_installation(
        self, organization_id: UUID, installation_id: UUID
    ) -> ConnectorInstallation | None:
        installation = self.installations.get(installation_id)
        return (
            installation
            if installation and installation.organization_id == organization_id
            else None
        )

    async def organization_for_external_installation(
        self, provider: str, external_account_id: str
    ) -> UUID | None:
        for installation in self.installations.values():
            if (
                installation.provider == provider
                and installation.external_account_id == external_account_id
            ):
                return installation.organization_id
        return None

    async def update_installation(self, installation: ConnectorInstallation) -> None:
        self.installations[installation.id] = installation

    async def add_repository(self, repository: RepositoryConnection) -> None:
        self.repositories[repository.id] = repository

    async def get_repository(
        self, organization_id: UUID, repository_id: UUID
    ) -> RepositoryConnection | None:
        repository = self.repositories.get(repository_id)
        return repository if repository and repository.organization_id == organization_id else None

    async def list_repositories(self, organization_id: UUID) -> tuple[RepositoryConnection, ...]:
        return tuple(
            repository
            for repository in self.repositories.values()
            if repository.organization_id == organization_id
        )

    async def record_webhook_delivery(
        self,
        *,
        provider: str,
        delivery_id: str,
        organization_id: UUID | None,
        event_name: str,
        payload_hash: str,
    ) -> bool:
        key = (provider, delivery_id)
        if key in self.webhook_deliveries:
            return False
        self.webhook_deliveries.add(key)
        return True

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        self.audits.append(
            {
                "organization_id": organization_id,
                "actor_subject": actor_subject,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details,
            }
        )
