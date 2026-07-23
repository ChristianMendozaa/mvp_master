from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from mvp_delivery.domain.models import Execution


@dataclass(frozen=True)
class DeliveryWorkflowInput:
    execution_id: str
    organization_id: str


@workflow.defn(name="delivery-workflow-v1")
class DeliveryWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._cancelled = False
        self._approval_actor: str | None = None

    @workflow.signal
    async def approve(self, actor_subject: str) -> None:
        self._approved = True
        self._approval_actor = actor_subject

    @workflow.signal
    async def cancel(self, actor_subject: str) -> None:
        del actor_subject
        self._cancelled = True

    @workflow.query
    def state(self) -> dict[str, str | bool | None]:
        return {
            "approved": self._approved,
            "cancelled": self._cancelled,
            "approval_actor": self._approval_actor,
        }

    @workflow.run
    async def run(self, input: DeliveryWorkflowInput) -> str:
        await workflow.execute_activity(
            "record-workflow-waiting",
            input,
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.wait_condition(lambda: self._approved or self._cancelled)
        if self._cancelled:
            await workflow.execute_activity(
                "cancel-and-cleanup-execution",
                input,
                start_to_close_timeout=timedelta(minutes=2),
            )
            return "CANCELLED"
        result = await workflow.execute_activity(
            "execute-delivery",
            input,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return str(result)


class TemporalWorkflowGateway:
    def __init__(self, client: Client, task_queue: str = "mvp-delivery-v1") -> None:
        self._client = client
        self._task_queue = task_queue

    async def start(self, execution: Execution) -> None:
        await self._client.start_workflow(
            DeliveryWorkflow.run,
            DeliveryWorkflowInput(
                execution_id=str(execution.id),
                organization_id=str(execution.organization_id),
            ),
            id=f"execution/{execution.id}",
            task_queue=self._task_queue,
        )

    async def approve(self, execution_id: UUID, actor_subject: str) -> None:
        handle = self._client.get_workflow_handle_for(
            DeliveryWorkflow.run, workflow_id=f"execution/{execution_id}"
        )
        await handle.signal(DeliveryWorkflow.approve, actor_subject)

    async def cancel(self, execution_id: UUID, actor_subject: str) -> None:
        handle = self._client.get_workflow_handle_for(
            DeliveryWorkflow.run, workflow_id=f"execution/{execution_id}"
        )
        await handle.signal(DeliveryWorkflow.cancel, actor_subject)
