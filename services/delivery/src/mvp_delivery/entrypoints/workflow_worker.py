import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from mvp_delivery.adapters.activities import DeliveryActivities
from mvp_delivery.adapters.temporal_workflow import DeliveryWorkflow
from mvp_delivery.settings import Settings


async def main() -> None:
    settings = Settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    activities = DeliveryActivities(settings)
    worker = Worker(
        client,
        task_queue="mvp-delivery-v1",
        workflows=[DeliveryWorkflow],
        activities=[
            activities.record_waiting,
            activities.cancel_execution,
            activities.execute_delivery,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
