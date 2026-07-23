from uuid import UUID, uuid4

from mvp_integrations.application.ports import IntegrationRepository, SourceControlProvider
from mvp_integrations.domain.errors import RepositoryAccessDenied
from mvp_integrations.domain.models import (
    ConnectorInstallation,
    InstallationStatus,
    PullRequestResult,
    RepositoryConnection,
)

GITHUB_MINIMUM_PERMISSIONS = (
    "metadata:read",
    "contents:read-write",
    "issues:read-write",
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

    async def connect(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        provider: str,
        external_account_id: str,
        account_login: str,
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

    async def create_pull_request(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        repository_id: UUID,
        title: str,
        body: str,
        head_branch: str,
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
