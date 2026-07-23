import asyncio
import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from mvp_delivery.settings import Settings

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000004")
POOL_ID = UUID("00000000-0000-0000-0000-000000000005")
RUNNER_ID = UUID("00000000-0000-0000-0000-000000000006")
OWNER_SUBJECT = "11111111-1111-1111-1111-111111111111"
RUNNER_CREDENTIAL = "local-runner-credential-only"


async def main() -> None:
    engine = create_async_engine(Settings().database_url)
    credential_hash = hashlib.sha256(RUNNER_CREDENTIAL.encode()).hexdigest()
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
                INSERT INTO provider_configurations (
                    id, organization_id, display_name, provider, runtime, model,
                    authentication_mode, secret_reference, enabled,
                    is_development_substitute
                )
                VALUES (
                    :id, :organization_id, 'Deterministic local agent',
                    'local', 'deterministic', 'deterministic-v1', 'NONE',
                    NULL, true, true
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": PROVIDER_ID, "organization_id": ORGANIZATION_ID},
        )
        await connection.execute(
            text(
                """
                INSERT INTO runner_pools (id, organization_id, name, runner_type)
                VALUES (:id, :organization_id, 'Local isolated runner', 'LOCAL')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": POOL_ID, "organization_id": ORGANIZATION_ID},
        )
        await connection.execute(
            text(
                """
                INSERT INTO runners (
                    id, organization_id, pool_id, name, capabilities,
                    credential_hash, status, last_seen_at
                )
                VALUES (
                    :id, :organization_id, :pool_id, 'compose-runner',
                    '["docker","deterministic"]'::jsonb,
                    :credential_hash, 'ONLINE', now()
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": RUNNER_ID,
                "organization_id": ORGANIZATION_ID,
                "pool_id": POOL_ID,
                "credential_hash": credential_hash,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO runner_credential_routing (
                    credential_hash, organization_id, runner_id
                )
                VALUES (:credential_hash, :organization_id, :runner_id)
                ON CONFLICT (credential_hash) DO NOTHING
                """
            ),
            {
                "credential_hash": credential_hash,
                "organization_id": ORGANIZATION_ID,
                "runner_id": RUNNER_ID,
            },
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
