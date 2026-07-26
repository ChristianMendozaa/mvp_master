import asyncio
import logging

import httpx
from mvp_common.contracts import SecretReference
from mvp_common.logging import configure_logging
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mvp_integrations.adapters.encrypted_file_secrets import EncryptedFileSecretStore
from mvp_integrations.adapters.github import (
    GitHubAppClient,
    GitHubInstallationCredentialProvider,
    GitHubSourceControl,
)
from mvp_integrations.adapters.postgres import PostgresIntegrationRepository
from mvp_integrations.application.service import IntegrationService
from mvp_integrations.domain.models import InstallationStatus
from mvp_integrations.settings import Settings

LOGGER = logging.getLogger(__name__)


async def reconcile_once(settings: Settings) -> None:
    if settings.secret_master_key_file is None:
        return
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    secrets = EncryptedFileSecretStore(
        settings.encrypted_secret_root, settings.secret_master_key_file
    )
    try:
        async with sessions() as route_session:
            routes = await PostgresIntegrationRepository(route_session).list_installation_routes()
        for organization_id, installation_id in routes:
            try:
                async with sessions() as session:
                    repository = PostgresIntegrationRepository(session)
                    installation = await repository.get_installation(
                        organization_id, installation_id
                    )
                    if (
                        installation is None
                        or installation.provider != "github"
                        or installation.status is not InstallationStatus.ACTIVE
                        or installation.provider_configuration_id is None
                    ):
                        continue
                    configuration = await repository.get_source_control_configuration(
                        installation.provider_configuration_id
                    )
                    if configuration is None or not configuration.enabled:
                        continue
                    private_reference = SecretReference(**configuration.private_key_reference)
                    async with httpx.AsyncClient(
                        base_url=configuration.api_base_url, timeout=30
                    ) as client:
                        app_client = GitHubAppClient(
                            client=client, api_version=configuration.api_version
                        )
                        service = IntegrationService(
                            repository,
                            {
                                "github": GitHubSourceControl(
                                    client=client,
                                    credential_provider=GitHubInstallationCredentialProvider(
                                        app_client=app_client,
                                        app_id=configuration.app_id,
                                        private_key_reference=private_reference,
                                        secrets=secrets,
                                    ),
                                    api_version=configuration.api_version,
                                )
                            },
                        )
                        await service.reconcile(
                            installation=installation,
                            actor_subject="github-reconciliation-worker",
                        )
                    await session.commit()
            except Exception:
                LOGGER.exception(
                    "GitHub installation reconciliation failed",
                    extra={"organization_id": str(organization_id)},
                )
    finally:
        await engine.dispose()


async def main() -> None:
    configure_logging()
    settings = Settings()
    while True:
        await reconcile_once(settings)
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
