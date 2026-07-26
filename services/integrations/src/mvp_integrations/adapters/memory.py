from datetime import datetime
from uuid import UUID

from mvp_integrations.application.ports import IntegrationRepository
from mvp_integrations.domain.models import (
    ConfigurationHealth,
    ConnectorInstallation,
    RepositoryConnection,
    SourceControlConfiguration,
)


class MemoryIntegrationRepository(IntegrationRepository):
    def __init__(self) -> None:
        self.installations: dict[UUID, ConnectorInstallation] = {}
        self.repositories: dict[UUID, RepositoryConnection] = {}
        self.webhook_deliveries: set[tuple[str, str]] = set()
        self.audits: list[dict[str, object]] = []
        self.configurations: dict[UUID, SourceControlConfiguration] = {}
        self.platform_audits: list[dict[str, object]] = []
        self.platform_setup_attempts: dict[str, tuple[str, datetime, bool]] = {}
        self.connector_setup_attempts: dict[tuple[UUID, str], tuple[str, UUID, datetime, bool]] = {}
        self.source_capability_redemptions: set[tuple[UUID, str]] = set()

    async def create_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, expires_at: datetime
    ) -> None:
        self.platform_setup_attempts[state_hash] = (actor_subject, expires_at, False)

    async def consume_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, now: datetime
    ) -> bool:
        attempt = self.platform_setup_attempts.get(state_hash)
        if not attempt or attempt[0] != actor_subject or attempt[2] or attempt[1] <= now:
            return False
        self.platform_setup_attempts[state_hash] = (attempt[0], attempt[1], True)
        return True

    async def create_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        configuration_id: UUID,
        expires_at: datetime,
    ) -> None:
        self.connector_setup_attempts[(organization_id, state_hash)] = (
            actor_subject,
            configuration_id,
            expires_at,
            False,
        )

    async def consume_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        now: datetime,
    ) -> UUID | None:
        key = (organization_id, state_hash)
        attempt = self.connector_setup_attempts.get(key)
        if not attempt or attempt[0] != actor_subject or attempt[3] or attempt[2] <= now:
            return None
        self.connector_setup_attempts[key] = (
            attempt[0],
            attempt[1],
            attempt[2],
            True,
        )
        return attempt[1]

    async def redeem_source_capability(
        self,
        organization_id: UUID,
        capability_id: str,
        expires_at: datetime,
    ) -> bool:
        del expires_at
        key = (organization_id, capability_id)
        if key in self.source_capability_redemptions:
            return False
        self.source_capability_redemptions.add(key)
        return True

    async def add_source_control_configuration(
        self, configuration: SourceControlConfiguration
    ) -> None:
        self.configurations[configuration.id] = configuration

    async def get_source_control_configuration(
        self, configuration_id: UUID
    ) -> SourceControlConfiguration | None:
        return self.configurations.get(configuration_id)

    async def source_control_configuration_for_app_id(
        self, provider: str, app_id: str
    ) -> SourceControlConfiguration | None:
        return next(
            (
                item
                for item in self.configurations.values()
                if item.provider == provider and item.app_id == app_id
            ),
            None,
        )

    async def list_source_control_configurations(
        self,
    ) -> tuple[SourceControlConfiguration, ...]:
        return tuple(self.configurations.values())

    async def update_source_control_configuration_health(
        self, configuration_id: UUID, health: str, enabled: bool
    ) -> None:
        configuration = self.configurations.get(configuration_id)
        if configuration:
            from dataclasses import replace

            self.configurations[configuration_id] = replace(
                configuration, health=ConfigurationHealth(health), enabled=enabled
            )

    async def record_platform_audit(
        self,
        *,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        self.platform_audits.append(
            {
                "actor_subject": actor_subject,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details,
            }
        )

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

    async def installation_for_external(
        self, organization_id: UUID, provider: str, external_account_id: str
    ) -> ConnectorInstallation | None:
        return next(
            (
                item
                for item in self.installations.values()
                if item.organization_id == organization_id
                and item.provider == provider
                and item.external_account_id == external_account_id
            ),
            None,
        )

    async def list_installation_routes(self) -> tuple[tuple[UUID, UUID], ...]:
        return tuple((item.organization_id, item.id) for item in self.installations.values())

    async def update_installation(self, installation: ConnectorInstallation) -> None:
        self.installations[installation.id] = installation

    async def add_repository(self, repository: RepositoryConnection) -> None:
        self.repositories[repository.id] = repository

    async def upsert_repository(self, repository: RepositoryConnection) -> None:
        existing = next(
            (
                item
                for item in self.repositories.values()
                if item.organization_id == repository.organization_id
                and item.installation_id == repository.installation_id
                and item.external_repository_id == repository.external_repository_id
            ),
            None,
        )
        if existing:
            del self.repositories[existing.id]
        self.repositories[repository.id] = repository

    async def revoke_repositories_except(
        self,
        organization_id: UUID,
        installation_id: UUID,
        active_external_ids: set[str],
        revoked_at: datetime,
    ) -> None:
        from dataclasses import replace

        from mvp_integrations.domain.models import RepositoryAccessStatus

        for repository_id, repository in tuple(self.repositories.items()):
            if (
                repository.organization_id == organization_id
                and repository.installation_id == installation_id
                and repository.external_repository_id not in active_external_ids
            ):
                self.repositories[repository_id] = replace(
                    repository,
                    access_status=RepositoryAccessStatus.REVOKED,
                    revoked_at=revoked_at,
                )

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
