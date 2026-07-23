import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from mvp_integrations.settings import Settings

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
INSTALLATION_ID = UUID("00000000-0000-0000-0000-000000000010")
REPOSITORY_ID = UUID("00000000-0000-0000-0000-000000000003")
OWNER_SUBJECT = "11111111-1111-1111-1111-111111111111"


async def main() -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.begin() as connection:
        await connection.execute(
            text("select set_config('app.current_organization_id', :value, true)"),
            {"value": str(ORGANIZATION_ID)},
        )
        await connection.execute(
            text(
                """
                INSERT INTO membership_projection (organization_id, subject, role, active)
                VALUES (:organization_id, :subject, 'OWNER', true)
                ON CONFLICT (organization_id, subject)
                DO UPDATE SET role = 'OWNER', active = true
                """
            ),
            {"organization_id": ORGANIZATION_ID, "subject": OWNER_SUBJECT},
        )
        await connection.execute(
            text(
                """
                INSERT INTO connector_installations (
                    id, organization_id, provider, external_account_id, account_login,
                    requested_permissions, is_development_substitute, status, created_at
                )
                VALUES (
                    :id, :organization_id, 'github-local', 'acme-local', 'Acme Local',
                    '["metadata:read","contents:read-write","issues:read-write",
                      "pull_requests:read-write","checks:read-write"]'::jsonb,
                    true, 'ACTIVE', :created_at
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": INSTALLATION_ID,
                "organization_id": ORGANIZATION_ID,
                "created_at": datetime.now(UTC),
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO installation_routing (
                    provider, external_account_id, organization_id, installation_id
                )
                VALUES ('github-local', 'acme-local', :organization_id, :installation_id)
                ON CONFLICT (provider, external_account_id) DO NOTHING
                """
            ),
            {
                "organization_id": ORGANIZATION_ID,
                "installation_id": INSTALLATION_ID,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO repository_connections (
                    id, organization_id, installation_id, external_repository_id,
                    owner, name, default_branch, clone_locator, is_private,
                    is_development_substitute, created_at
                )
                VALUES (
                    :id, :organization_id, :installation_id, 'local-acme-sample',
                    'acme-local', 'sample-webapp', 'main',
                    'file:///fixtures/sample-webapp.git', true, true, :created_at
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": REPOSITORY_ID,
                "organization_id": ORGANIZATION_ID,
                "installation_id": INSTALLATION_ID,
                "created_at": datetime.now(UTC),
            },
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
