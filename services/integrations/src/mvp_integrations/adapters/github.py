import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx
from mvp_common.contracts import ExternalReference

from mvp_integrations.application.ports import RepositoryDescriptor
from mvp_integrations.domain.models import (
    ConnectorInstallation,
    PullRequestResult,
    RepositoryConnection,
)


def verify_webhook_signature(*, body: bytes, signature_header: str, secret: bytes) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    supplied = signature_header.removeprefix("sha256=")
    if len(supplied) != 64:
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


@dataclass(frozen=True, slots=True)
class GitHubCredential:
    token: str


class GitHubSourceControl:
    provider_name = "github"
    is_development_substitute = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        credential_provider: Any,
    ) -> None:
        self._client = client
        self._credential_provider = credential_provider

    async def _headers(self, external_account_id: str) -> dict[str, str]:
        credential: GitHubCredential = await self._credential_provider.for_installation(
            external_account_id
        )
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {credential.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def repositories(self, external_account_id: str) -> tuple[RepositoryDescriptor, ...]:
        response = await self._client.get(
            "/installation/repositories",
            headers=await self._headers(external_account_id),
        )
        response.raise_for_status()
        payload = response.json()
        return tuple(
            RepositoryDescriptor(
                external_id=str(item["id"]),
                owner=str(item["owner"]["login"]),
                name=str(item["name"]),
                default_branch=str(item["default_branch"]),
                clone_locator=str(item["clone_url"]),
                is_private=bool(item["private"]),
            )
            for item in payload["repositories"]
        )

    async def create_pull_request(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        idempotency_key: str,
    ) -> PullRequestResult:
        response = await self._client.post(
            f"/repos/{repository.full_name}/pulls",
            headers={
                **(await self._headers(installation.external_account_id)),
                "Idempotency-Key": idempotency_key,
            },
            json={"title": title, "body": body, "head": head_branch, "base": base_branch},
        )
        response.raise_for_status()
        payload = response.json()
        return PullRequestResult(
            reference=ExternalReference(
                provider=self.provider_name,
                account_id=installation.external_account_id,
                repository=repository.full_name,
                resource_type="pull_request",
                external_id=str(payload["number"]),
            ),
            title=title,
            url=str(payload["html_url"]),
            head_branch=head_branch,
            base_branch=base_branch,
            is_development_substitute=False,
        )

    async def add_comment(
        self,
        *,
        installation: ConnectorInstallation,
        external_reference_id: str,
        body: str,
        idempotency_key: str,
    ) -> None:
        raise NotImplementedError(
            "real comment routing requires an external reference with repository context"
        )
