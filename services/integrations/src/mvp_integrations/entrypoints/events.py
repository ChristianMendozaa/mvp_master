import asyncio

import nats
from mvp_common.contracts import EventEnvelope
from nats.errors import TimeoutError as NatsTimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mvp_integrations.adapters.postgres import PostgresIntegrationRepository
from mvp_integrations.settings import Settings


async def main() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    connection = await nats.connect(servers=[settings.nats_url])
    jetstream = connection.jetstream()
    subscription = await jetstream.pull_subscribe(
        "events.com.mvp.membership.changed.v1",
        durable="integrations-membership-v1",
        stream="DOMAIN_EVENTS",
    )
    try:
        while True:
            try:
                messages = await subscription.fetch(20, timeout=5)
            except NatsTimeoutError:
                continue
            for message in messages:
                event = EventEnvelope.model_validate_json(message.data)
                async with sessions() as session:
                    repository = PostgresIntegrationRepository(session)
                    accepted = await repository.record_inbox(
                        event.id, event.organization_id, event.type
                    )
                    if accepted:
                        await repository.upsert_membership(
                            event.organization_id,
                            str(event.data["subject"]),
                            str(event.data["role"]),
                            bool(event.data["active"]),
                        )
                    await session.commit()
                await message.ack()
    finally:
        await connection.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
