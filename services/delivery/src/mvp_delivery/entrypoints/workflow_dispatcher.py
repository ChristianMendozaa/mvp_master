import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from mvp_delivery.adapters.postgres import WorkflowCommandRow
from mvp_delivery.adapters.temporal_workflow import (
    DeliveryWorkflow,
    DeliveryWorkflowInput,
)
from mvp_delivery.settings import Settings


async def main() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    while True:
        dispatched = 0
        async with sessions() as session:
            commands = (
                await session.scalars(
                    select(WorkflowCommandRow)
                    .where(WorkflowCommandRow.dispatched_at.is_(None))
                    .order_by(WorkflowCommandRow.id)
                    .with_for_update(skip_locked=True)
                    .limit(50)
                )
            ).all()
            for command in commands:
                workflow_id = f"execution/{command.execution_id}"
                if command.command == "START":
                    with suppress(WorkflowAlreadyStartedError):
                        await client.start_workflow(
                            DeliveryWorkflow.run,
                            DeliveryWorkflowInput(
                                execution_id=str(command.execution_id),
                                organization_id=str(command.organization_id),
                            ),
                            id=workflow_id,
                            task_queue="mvp-delivery-v1",
                        )
                else:
                    handle = client.get_workflow_handle(workflow_id)
                    if command.command == "APPROVE":
                        await handle.signal(
                            DeliveryWorkflow.approve, command.actor_subject or "unknown"
                        )
                    elif command.command == "CANCEL":
                        await handle.signal(
                            DeliveryWorkflow.cancel, command.actor_subject or "unknown"
                        )
                command.dispatched_at = datetime.now(UTC)
                dispatched += 1
            await session.commit()
        await asyncio.sleep(0.2 if dispatched else 1)


if __name__ == "__main__":
    asyncio.run(main())
