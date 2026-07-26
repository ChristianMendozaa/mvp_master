"""Unit tests for `LeasedSecretResolver` against mocked HTTP transports — no live
delivery/integrations services or credentials required (AGENTS.md).
"""

import httpx
import pytest
from mvp_common.contracts import SecretReference
from mvp_runner.adapters.control_client import (
    ModelCredentialClient,
    RunnerControlClient,
    RunnerIdentity,
)
from mvp_runner.adapters.leased_secret_resolver import LeasedSecretResolver
from mvp_runner.domain.errors import SecretResolutionFailed


def _control_client(capability_calls: list[str]) -> RunnerControlClient:
    def handler(request: httpx.Request) -> httpx.Response:
        capability_calls.append(str(request.url))
        return httpx.Response(200, json={"capability": "capability-token-1"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return RunnerControlClient("http://delivery.invalid", http_client)


def _credentials_client(
    *, value: str | None = None, status_code: int = 200
) -> ModelCredentialClient:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        if status_code != 200:
            return httpx.Response(status_code, json={"detail": "error"})
        return httpx.Response(200, json={"value": value})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ModelCredentialClient("http://integrations.invalid", http_client)


async def test_resolve_mints_a_capability_and_exchanges_it() -> None:
    capability_calls: list[str] = []
    control = _control_client(capability_calls)
    credentials = _credentials_client(value="sk-resolved-secret")
    resolver = LeasedSecretResolver(
        identity=RunnerIdentity(runner_id="runner-1", credential="cred"),
        job_id="job-1",
        control=control,
        credentials=credentials,
    )
    reference = SecretReference(store="encrypted-file", namespace="model-credentials/org", key="k1")
    value = await resolver.resolve(reference)
    assert value == "sk-resolved-secret"
    assert len(capability_calls) == 1
    assert "job-1" in capability_calls[0]
    assert "model-capability" in capability_calls[0]


async def test_resolve_mints_a_fresh_capability_each_call_no_caching() -> None:
    capability_calls: list[str] = []
    control = _control_client(capability_calls)
    credentials = _credentials_client(value="sk-resolved-secret")
    resolver = LeasedSecretResolver(
        identity=RunnerIdentity(runner_id="runner-1", credential="cred"),
        job_id="job-1",
        control=control,
        credentials=credentials,
    )
    reference = SecretReference(store="encrypted-file", namespace="model-credentials/org", key="k1")
    await resolver.resolve(reference)
    await resolver.resolve(reference)
    assert len(capability_calls) == 2


async def test_failure_from_either_hop_is_normalized() -> None:
    capability_calls: list[str] = []
    control = _control_client(capability_calls)
    credentials = _credentials_client(status_code=409)
    resolver = LeasedSecretResolver(
        identity=RunnerIdentity(runner_id="runner-1", credential="cred"),
        job_id="job-1",
        control=control,
        credentials=credentials,
    )
    reference = SecretReference(store="encrypted-file", namespace="model-credentials/org", key="k1")
    with pytest.raises(SecretResolutionFailed):
        await resolver.resolve(reference)
