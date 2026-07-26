from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mvp_common.contracts import SecretReference

from mvp_integrations.application.ports import IntegrationRepository, SourceControlProvider
from mvp_integrations.domain.errors import RepositoryAccessDenied
from mvp_integrations.domain.models import (
    ConnectorInstallation,
    InstallationStatus,
    PullRequestResult,
    RepositoryAccessStatus,
    RepositoryConnection,
    SourceControlConfiguration,
    WebhookMode,
)

GITHUB_MINIMUM_PERMISSIONS = (
    "metadata:read",
    "contents:read-write",
    "pull_requests:read-write",
    "checks:read-write",
)


class IntegrationService:
    def __init__(
        self,
        repository: IntegrationRepository,
        providers: dict[str, SourceControlProvider],
    ) -> None:
        self._repository = repository
        self._providers = providers

    async def configure_source_control(
        self,
        *,
        configuration_id: UUID,
        actor_subject: str,
        display_name: str,
        provider: str,
        web_base_url: str,
        api_base_url: str,
        api_version: str,
        app_id: str,
        client_id: str,
        app_slug: str,
        private_key_reference: SecretReference,
        client_secret_reference: SecretReference,
        webhook_secret_reference: SecretReference,
        webhook_mode: WebhookMode,
    ) -> SourceControlConfiguration:
        configuration = SourceControlConfiguration(
            id=configuration_id,
            display_name=display_name,
            provider=provider,
            web_base_url=web_base_url,
            api_base_url=api_base_url,
            api_version=api_version,
            app_id=app_id,
            client_id=client_id,
            app_slug=app_slug,
            private_key_reference=private_key_reference.model_dump(),
            client_secret_reference=client_secret_reference.model_dump(),
            webhook_secret_reference=webhook_secret_reference.model_dump(),
            webhook_mode=webhook_mode,
            enabled=True,
        )
        await self._repository.add_source_control_configuration(configuration)
        await self._repository.record_platform_audit(
            actor_subject=actor_subject,
            action="source_control_configuration.created",
            target_type="source_control_configuration",
            target_id=configuration.id,
            details={"provider": provider, "webhook_mode": webhook_mode.value},
        )
        return configuration

    async def connect(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        provider: str,
        external_account_id: str,
        account_login: str,
        provider_configuration_id: UUID | None = None,
        granted_permissions: tuple[str, ...] = (),
        repository_selection: str = "SELECTED",
    ) -> tuple[ConnectorInstallation, tuple[RepositoryConnection, ...]]:
        adapter = self._providers[provider]
        installation = ConnectorInstallation(
            id=uuid4(),
            organization_id=organization_id,
            provider=provider,
            external_account_id=external_account_id,
            account_login=account_login,
            requested_permissions=GITHUB_MINIMUM_PERMISSIONS,
            is_development_substitute=adapter.is_development_substitute,
            provider_configuration_id=provider_configuration_id,
            granted_permissions=granted_permissions,
            repository_selection=repository_selection,
        )
        await self._repository.add_installation(installation)
        connected: list[RepositoryConnection] = []
        for descriptor in await adapter.repositories(external_account_id):
            repository = RepositoryConnection(
                id=uuid4(),
                organization_id=organization_id,
                installation_id=installation.id,
                external_repository_id=descriptor.external_id,
                owner=descriptor.owner,
                name=descriptor.name,
                default_branch=descriptor.default_branch,
                clone_locator=descriptor.clone_locator,
                is_private=descriptor.is_private,
                is_development_substitute=adapter.is_development_substitute,
            )
            await self._repository.add_repository(repository)
            connected.append(repository)
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="connector.connected",
            target_type="connector_installation",
            target_id=installation.id,
            details={
                "provider": provider,
                "repository_count": len(connected),
                "development_substitute": adapter.is_development_substitute,
            },
        )
        return installation, tuple(connected)

    async def reconcile(
        self,
        *,
        installation: ConnectorInstallation,
        actor_subject: str,
    ) -> tuple[RepositoryConnection, ...]:
        adapter = self._providers[installation.provider]
        now = datetime.now(UTC)
        connected: list[RepositoryConnection] = []
        active_ids: set[str] = set()
        existing = {
            item.external_repository_id: item
            for item in await self._repository.list_repositories(installation.organization_id)
            if item.installation_id == installation.id
        }
        for descriptor in await adapter.repositories(installation.external_account_id):
            active_ids.add(descriptor.external_id)
            previous = existing.get(descriptor.external_id)
            repository = RepositoryConnection(
                id=previous.id if previous else uuid4(),
                organization_id=installation.organization_id,
                installation_id=installation.id,
                external_repository_id=descriptor.external_id,
                owner=descriptor.owner,
                name=descriptor.name,
                default_branch=descriptor.default_branch,
                clone_locator=descriptor.clone_locator,
                is_private=descriptor.is_private,
                is_development_substitute=adapter.is_development_substitute,
                access_status=RepositoryAccessStatus.ACTIVE,
                last_seen_at=now,
                revoked_at=None,
                created_at=previous.created_at if previous else now,
            )
            await self._repository.upsert_repository(repository)
            connected.append(repository)
        await self._repository.revoke_repositories_except(
            installation.organization_id,
            installation.id,
            active_ids,
            now,
        )
        await self._repository.update_installation(replace(installation, last_reconciled_at=now))
        await self._repository.record_audit(
            organization_id=installation.organization_id,
            actor_subject=actor_subject,
            action="connector.reconciled",
            target_type="connector_installation",
            target_id=installation.id,
            details={"repository_count": len(connected)},
        )
        return tuple(connected)

    async def create_pull_request(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        repository_id: UUID,
        title: str,
        body: str,
        head_branch: str,
        head_sha: str | None,
        idempotency_key: str,
    ) -> PullRequestResult:
        repository = await self._repository.get_repository(organization_id, repository_id)
        if repository is None:
            raise RepositoryAccessDenied("repository is not connected for this organization")
        installation = await self._repository.get_installation(
            organization_id, repository.installation_id
        )
        if installation is None or installation.status is not InstallationStatus.ACTIVE:
            raise RepositoryAccessDenied("connector installation is not active")
        adapter = self._providers[installation.provider]
        result = await adapter.create_pull_request(
            installation=installation,
            repository=repository,
            title=title,
            body=body,
            head_branch=head_branch,
            base_branch=repository.default_branch,
            idempotency_key=idempotency_key,
        )
        if head_sha:
            await adapter.create_check_run(
                installation=installation,
                repository=repository,
                head_sha=head_sha,
                name="MVP Master independent verification",
                summary="Agent output was independently validated before publication.",
                idempotency_key=f"{idempotency_key}:verification",
            )
        await self._repository.record_audit(
            organization_id=organization_id,
            actor_subject=actor_subject,
            action="pull_request.created",
            target_type="repository_connection",
            target_id=repository.id,
            details={
                "external_id": result.reference.external_id,
                "development_substitute": result.is_development_substitute,
            },
        )
        return result
