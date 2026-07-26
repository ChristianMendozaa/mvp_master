import hashlib
import hmac
from uuid import uuid4

from mvp_integrations.adapters.github import verify_webhook_signature
from mvp_integrations.adapters.local_source_control import LocalSourceControl
from mvp_integrations.adapters.memory import MemoryIntegrationRepository
from mvp_integrations.application.service import IntegrationService


async def test_local_connector_is_explicit_and_pull_request_is_idempotent() -> None:
    repository = MemoryIntegrationRepository()
    adapter = LocalSourceControl()
    service = IntegrationService(repository, {"github-local": adapter})
    organization_id = uuid4()
    installation, repositories = await service.connect(
        organization_id=organization_id,
        actor_subject="owner@example.test",
        provider="github-local",
        external_account_id="acme-local",
        account_login="Acme Local",
    )
    assert installation.is_development_substitute is True
    assert repositories[0].is_development_substitute is True

    first = await service.create_pull_request(
        organization_id=organization_id,
        actor_subject="delivery-service",
        repository_id=repositories[0].id,
        title="Show delivery status",
        body="Verified locally.",
        head_branch="agent/work-item/execution",
        head_sha="1" * 40,
        idempotency_key="execution-1",
    )
    second = await service.create_pull_request(
        organization_id=organization_id,
        actor_subject="delivery-service",
        repository_id=repositories[0].id,
        title="Show delivery status",
        body="Verified locally.",
        head_branch="agent/work-item/execution",
        head_sha="1" * 40,
        idempotency_key="execution-1",
    )
    assert first == second
    assert first.is_development_substitute is True


def test_webhook_signature_is_constant_time_compatible() -> None:
    body = b'{"action":"opened"}'
    secret = b"synthetic-test-secret"
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(
        body=body,
        signature_header=f"sha256={digest}",
        secret=secret,
    )
    assert not verify_webhook_signature(
        body=body,
        signature_header="sha256=" + ("0" * 64),
        secret=secret,
    )
