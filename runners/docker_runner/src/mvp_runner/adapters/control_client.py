from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class RunnerIdentity:
    runner_id: str
    credential: str


class RunnerControlClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def enroll(
        self, *, token: str, name: str, capabilities: tuple[str, ...]
    ) -> RunnerIdentity:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/enroll",
            json={"enrollment_token": token, "name": name, "capabilities": capabilities},
        )
        response.raise_for_status()
        payload = response.json()
        return RunnerIdentity(
            runner_id=str(payload["runner_id"]),
            credential=str(payload["runner_credential"]),
        )

    async def lease_job(self, identity: RunnerIdentity) -> dict[str, Any] | None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/jobs/lease",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=35,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return dict(response.json())

    async def complete_job(
        self, identity: RunnerIdentity, job_id: str, result: dict[str, Any]
    ) -> None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/jobs/{job_id}/complete",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            json=result,
            timeout=35,
        )
        response.raise_for_status()

    async def heartbeat_job(self, identity: RunnerIdentity, job_id: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/jobs/{job_id}/heartbeat",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=10,
        )
        response.raise_for_status()

    async def source_capability(self, identity: RunnerIdentity, job_id: str, purpose: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/jobs/{job_id}/source-capability",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
                "X-Source-Purpose": purpose,
            },
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["capability"])

    async def model_capability(self, identity: RunnerIdentity, job_id: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/jobs/{job_id}/model-capability",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["capability"])

    async def lease_provider_verification(self, identity: RunnerIdentity) -> dict[str, Any] | None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/provider-verifications/lease",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=35,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return dict(response.json())

    async def heartbeat_provider_verification(
        self, identity: RunnerIdentity, verification_id: str
    ) -> None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/provider-verifications/{verification_id}/heartbeat",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=10,
        )
        response.raise_for_status()

    async def provider_verification_model_capability(
        self, identity: RunnerIdentity, verification_id: str
    ) -> str:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/provider-verifications/{verification_id}/model-capability",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["capability"])

    async def complete_provider_verification(
        self,
        identity: RunnerIdentity,
        verification_id: str,
        result: dict[str, Any],
    ) -> None:
        response = await self._client.post(
            f"{self._base_url}/runner/v1/provider-verifications/{verification_id}/complete",
            headers={
                "Authorization": f"Runner {identity.credential}",
                "X-Runner-ID": identity.runner_id,
            },
            json=result,
            timeout=35,
        )
        response.raise_for_status()


class SourceCredentialClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def exchange(self, capability: str) -> dict[str, str]:
        response = await self._client.post(
            f"{self._base_url}/internal/v1/source-credentials/exchange",
            json={"capability": capability},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return {str(key): str(value) for key, value in payload.items()}


class ModelCredentialClient:
    """Redeems a model-capability token for the plaintext value it names.

    Deliberately returns a bare `str`, not a dict — there is nothing else in the
    response and a dict shape invites accidentally logging the whole object.
    """

    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def exchange(self, capability: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/internal/v1/model-credentials/exchange",
            json={"capability": capability},
            timeout=30,
        )
        response.raise_for_status()
        return str(response.json()["value"])
