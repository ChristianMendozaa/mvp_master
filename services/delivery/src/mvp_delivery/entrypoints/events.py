import asyncio
from uuid import UUID

import nats
from mvp_common.contracts import EventEnvelope
from nats.errors import TimeoutError as NatsTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mvp_delivery.adapters.postgres import (
    PostgresDeliveryRepository,
    PostgresWorkflowGateway,
)
from mvp_delivery.application.service import DeliveryService
from mvp_delivery.domain.models import ExecutionBudget
from mvp_delivery.settings import Settings


async def process_event(event: EventEnvelope, sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        repository = PostgresDeliveryRepository(session)
        if not await repository.record_inbox(event.id, event.organization_id, event.type):
            await session.rollback()
            return
        if event.type == "com.mvp.membership.changed.v1":
            await repository.upsert_membership(
                event.organization_id,
                str(event.data["subject"]),
                str(event.data["role"]),
                bool(event.data["active"]),
            )
        elif event.type == "com.mvp.work_item.ready.v1":
            data = event.data
            budget = dict(data["budget"])
            service = DeliveryService(repository, PostgresWorkflowGateway(session))
            await service.accept_ready_work_item(
                organization_id=event.organization_id,
                project_id=UUID(str(data["project_id"])),
                work_item_id=UUID(str(data["work_item_id"])),
                title=str(data["title"]),
                description=str(data["description"]),
                acceptance_criteria=tuple(str(item) for item in data["acceptance_criteria"]),
                repository_connection_id=UUID(str(data["repository_connection_id"])),
                provider_configuration_id=UUID(str(data["provider_configuration_id"])),
                runner_pool_id=UUID(str(data["runner_pool_id"])),
                budget=ExecutionBudget(
                    max_duration_seconds=int(budget["max_duration_seconds"]),
                    max_attempts=int(budget["max_attempts"]),
                    max_turns=int(budget["max_turns"]),
                    max_cost_minor=int(budget["max_cost_minor"]),
                    currency=str(budget["currency"]),
                ),
                correlation_id=event.correlation_id,
            )
        await session.commit()


async def main() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    connection = await nats.connect(servers=[settings.nats_url])
    jetstream = connection.jetstream()
    subscription = await jetstream.pull_subscribe(
        "events.com.mvp.>",
        durable="delivery-domain-events-v1",
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
                await process_event(event, sessions)
                await message.ack()
    finally:
        await connection.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
