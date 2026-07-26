import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jwt
from mvp_common.contracts import ExternalReference, SecretReference

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
    expires_at: str | None = None


class GitHubPrivateKeyResolver(Protocol):
    async def get(self, reference: SecretReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class GitHubManifestResult:
    app_id: str
    client_id: str
    client_secret: bytes
    pem: bytes
    webhook_secret: bytes
    app_slug: str


class GitHubAppClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_version: str,
    ) -> None:
        self._client = client
        self._api_version = api_version

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self._api_version,
        }

    async def convert_manifest(self, code: str) -> GitHubManifestResult:
        response = await self._client.post(
            f"/app-manifests/{code}/conversions",
            headers=self.headers,
        )
        response.raise_for_status()
        payload = response.json()
        return GitHubManifestResult(
            app_id=str(payload["id"]),
            client_id=str(payload["client_id"]),
            client_secret=str(payload["client_secret"]).encode(),
            pem=str(payload["pem"]).encode(),
            webhook_secret=str(payload["webhook_secret"]).encode(),
            app_slug=str(payload["slug"]),
        )

    async def app_jwt(self, app_id: str, private_key: bytes) -> str:
        now = int(time.time())
        value = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": app_id},
            private_key,
            algorithm="RS256",
        )
        return str(value)

    async def installation(
        self, installation_id: str, app_id: str, private_key: bytes
    ) -> dict[str, Any]:
        token = await self.app_jwt(app_id, private_key)
        response = await self._client.get(
            f"/app/installations/{installation_id}",
            headers={**self.headers, "Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return dict(response.json())

    async def app(self, app_id: str, private_key: bytes) -> dict[str, Any]:
        token = await self.app_jwt(app_id, private_key)
        response = await self._client.get(
            "/app",
            headers={**self.headers, "Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return dict(response.json())

    async def installation_token(
        self,
        *,
        installation_id: str,
        app_id: str,
        private_key: bytes,
        repository_id: str | None = None,
        permissions: dict[str, str] | None = None,
    ) -> GitHubCredential:
        app_token = await self.app_jwt(app_id, private_key)
        body: dict[str, object] = {}
        if repository_id:
            body["repository_ids"] = [int(repository_id)]
        if permissions:
            body["permissions"] = permissions
        response = await self._client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={**self.headers, "Authorization": f"Bearer {app_token}"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        return GitHubCredential(
            token=str(payload["token"]),
            expires_at=str(payload.get("expires_at")) if payload.get("expires_at") else None,
        )


class GitHubInstallationCredentialProvider:
    def __init__(
        self,
        *,
        app_client: GitHubAppClient,
        app_id: str,
        private_key_reference: SecretReference,
        secrets: GitHubPrivateKeyResolver,
    ) -> None:
        self._app_client = app_client
        self._app_id = app_id
        self._private_key_reference = private_key_reference
        self._secrets = secrets

    async def for_installation(
        self,
        external_account_id: str,
        *,
        repository_id: str | None = None,
        permissions: dict[str, str] | None = None,
    ) -> GitHubCredential:
        return await self._app_client.installation_token(
            installation_id=external_account_id,
            app_id=self._app_id,
            private_key=await self._secrets.get(self._private_key_reference),
            repository_id=repository_id,
            permissions=permissions,
        )


class GitHubSourceControl:
    provider_name = "github"
    is_development_substitute = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        credential_provider: Any,
        api_version: str = "2026-03-10",
    ) -> None:
        self._client = client
        self._credential_provider = credential_provider
        self._api_version = api_version

    async def _headers(
        self,
        external_account_id: str,
        *,
        repository_id: str | None = None,
        permissions: dict[str, str] | None = None,
    ) -> dict[str, str]:
        credential: GitHubCredential = await self._credential_provider.for_installation(
            external_account_id,
            repository_id=repository_id,
            permissions=permissions,
        )
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {credential.token}",
            "X-GitHub-Api-Version": self._api_version,
        }

    async def repositories(self, external_account_id: str) -> tuple[RepositoryDescriptor, ...]:
        descriptors: list[RepositoryDescriptor] = []
        headers = await self._headers(external_account_id, permissions={"metadata": "read"})
        for page in range(1, 101):
            response = await self._client.get(
                "/installation/repositories",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            items = response.json()["repositories"]
            descriptors.extend(
                RepositoryDescriptor(
                    external_id=str(item["id"]),
                    owner=str(item["owner"]["login"]),
                    name=str(item["name"]),
                    default_branch=str(item["default_branch"]),
                    clone_locator=str(item["clone_url"]),
                    is_private=bool(item["private"]),
                )
                for item in items
            )
            if len(items) < 100:
                break
        return tuple(descriptors)

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
        headers = await self._headers(
            installation.external_account_id,
            repository_id=repository.external_repository_id,
            permissions={"pull_requests": "write"},
        )
        existing_response = await self._client.get(
            f"/repos/{repository.full_name}/pulls",
            headers=headers,
            params={
                "state": "all",
                "head": f"{repository.owner}:{head_branch}",
                "base": base_branch,
                "per_page": 1,
            },
        )
        existing_response.raise_for_status()
        existing = existing_response.json()
        if existing:
            payload = existing[0]
        else:
            response = await self._client.post(
                f"/repos/{repository.full_name}/pulls",
                headers=headers,
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

    async def create_check_run(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        head_sha: str,
        name: str,
        summary: str,
        idempotency_key: str,
    ) -> None:
        response = await self._client.post(
            f"/repos/{repository.full_name}/check-runs",
            headers=await self._headers(
                installation.external_account_id,
                repository_id=repository.external_repository_id,
                permissions={"checks": "write"},
            ),
            json={
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": "success",
                "external_id": idempotency_key,
                "output": {"title": name, "summary": summary},
            },
        )
        response.raise_for_status()
