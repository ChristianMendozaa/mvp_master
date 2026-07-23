import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from mvp_control_plane.settings import Settings

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000002")
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
                INSERT INTO organizations (id, name, created_at)
                VALUES (:id, 'Acme Local', :created_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": ORGANIZATION_ID, "created_at": datetime.now(UTC)},
        )
        await connection.execute(
            text(
                """
                INSERT INTO memberships (organization_id, subject, role)
                VALUES (:organization_id, :subject, 'OWNER')
                ON CONFLICT (organization_id, subject) DO UPDATE SET role = 'OWNER'
                """
            ),
            {"organization_id": ORGANIZATION_ID, "subject": OWNER_SUBJECT},
        )
        await connection.execute(
            text(
                """
                INSERT INTO membership_routing (subject, organization_id, role)
                VALUES (:subject, :organization_id, 'OWNER')
                ON CONFLICT (subject, organization_id) DO UPDATE SET role = 'OWNER'
                """
            ),
            {"organization_id": ORGANIZATION_ID, "subject": OWNER_SUBJECT},
        )
        await connection.execute(
            text(
                """
                INSERT INTO projects (
                    id, organization_id, name, description,
                    execution_approval_required, created_at
                )
                VALUES (
                    :id, :organization_id, 'Client Portal',
                    'Local vertical-slice project', true, :created_at
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": PROJECT_ID,
                "organization_id": ORGANIZATION_ID,
                "created_at": datetime.now(UTC),
            },
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
