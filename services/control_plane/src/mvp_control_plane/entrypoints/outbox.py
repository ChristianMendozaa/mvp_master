import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime

import nats
from nats.errors import Error as NatsError
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mvp_control_plane.adapters.postgres import OutboxRoutingRow, OutboxRow
from mvp_control_plane.settings import Settings


async def publish_batch() -> int:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    connection = await nats.connect(servers=[settings.nats_url])
    jetstream = connection.jetstream()
    with suppress(NatsError):
        await jetstream.add_stream(name="DOMAIN_EVENTS", subjects=["events.>"])
    published = 0
    try:
        async with sessions() as session:
            routes = (
                await session.scalars(
                    select(OutboxRoutingRow).order_by(OutboxRoutingRow.event_id).limit(100)
                )
            ).all()
            for route in routes:
                await session.execute(
                    text("select set_config('app.current_organization_id', :value, true)"),
                    {"value": str(route.organization_id)},
                )
                event = await session.get(OutboxRow, route.event_id)
                if event is None:
                    await session.delete(route)
                    continue
                payload = json.dumps(event.payload, separators=(",", ":")).encode()
                await jetstream.publish(
                    f"events.{event.event_type}",
                    payload,
                    headers={"Nats-Msg-Id": str(event.id)},
                )
                event.published_at = datetime.now(UTC)
                await session.execute(
                    delete(OutboxRoutingRow).where(OutboxRoutingRow.event_id == route.event_id)
                )
                published += 1
            await session.commit()
    finally:
        await connection.close()
        await engine.dispose()
    return published


async def main() -> None:
    while True:
        try:
            count = await publish_batch()
        except Exception:
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(0.2 if count else 1)


if __name__ == "__main__":
    asyncio.run(main())
