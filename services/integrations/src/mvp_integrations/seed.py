import asyncio
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from mvp_integrations.settings import Settings

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
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
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
