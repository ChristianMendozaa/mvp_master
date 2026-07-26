import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from mvp_common.contracts import SecretReference
from mvp_common.logging import configure_logging
from mvp_observability import configure_observability
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mvp_integrations.adapters.encrypted_file_secrets import EncryptedFileSecretStore
from mvp_integrations.adapters.github import (
    GitHubAppClient,
    GitHubInstallationCredentialProvider,
    GitHubSourceControl,
    verify_webhook_signature,
)
from mvp_integrations.adapters.local_source_control import LocalSourceControl
from mvp_integrations.adapters.oidc import Principal, PrincipalProvider
from mvp_integrations.adapters.postgres import PostgresIntegrationRepository
from mvp_integrations.application.service import IntegrationService
from mvp_integrations.domain.models import (
    InstallationStatus,
    RepositoryAccessStatus,
    WebhookMode,
)
from mvp_integrations.settings import Settings


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionCreate(RequestModel):
    external_account_id: str = Field(min_length=1, max_length=256)
    account_login: str = Field(min_length=1, max_length=256)
    provider: str = "github-local"


class PullRequestCreate(RequestModel):
    title: str = Field(min_length=2, max_length=300)
    body: str = Field(max_length=10000)
    head_branch: str = Field(pattern=r"^[A-Za-z0-9._/-]+$", max_length=250)
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")


class InternalPullRequestCreate(PullRequestCreate):
    organization_id: UUID
    repository_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=256)


class GitHubManifestStart(RequestModel):
    display_name: str = Field(default="MVP Master GitHub", min_length=2, max_length=200)
    owner: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,39}$")
    webhook_mode: WebhookMode = WebhookMode.POLLING


class GitHubManifestComplete(RequestModel):
    state: str = Field(min_length=32, max_length=256)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{8,512}$")
    display_name: str = Field(default="MVP Master GitHub", min_length=2, max_length=200)
    webhook_mode: WebhookMode = WebhookMode.POLLING


class GitHubInstallationStart(RequestModel):
    configuration_id: UUID


class GitHubInstallationComplete(RequestModel):
    state: str = Field(min_length=32, max_length=256)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{8,512}$")
    installation_id: str = Field(pattern=r"^[0-9]{1,32}$")


class SourceCredentialExchange(RequestModel):
    capability: str = Field(min_length=64, max_length=4096)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    configure_logging()
    engine = create_async_engine(resolved.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    principals = PrincipalProvider(resolved)
    local_adapter = LocalSourceControl()

    def encrypted_secrets() -> EncryptedFileSecretStore:
        if resolved.secret_master_key_file is None:
            raise HTTPException(
                status_code=503,
                detail="encrypted secret store is not configured",
            )
        try:
            return EncryptedFileSecretStore(
                resolved.encrypted_secret_root,
                resolved.secret_master_key_file,
            )
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail="encrypted secret store is unavailable",
            ) from error

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(
        title="MVP Master Integrations",
        version="1.0.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    configure_observability(app, engine, service_name=resolved.service_name)

    async def repository() -> AsyncIterator[PostgresIntegrationRepository]:
        async with sessions() as session:
            try:
                yield PostgresIntegrationRepository(session)
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    Repo = Annotated[PostgresIntegrationRepository, Depends(repository)]
    PrincipalDependency = Annotated[Principal, Depends(principals.authenticate)]

    def service(repo: Repo) -> IntegrationService:
        return IntegrationService(repo, {"github-local": local_adapter})

    Service = Annotated[IntegrationService, Depends(service)]

    @asynccontextmanager
    async def service_for_repository(
        repo: PostgresIntegrationRepository,
        organization_id: UUID,
        repository_id: UUID,
    ) -> AsyncIterator[IntegrationService]:
        connected_repository = await repo.get_repository(organization_id, repository_id)
        if connected_repository is None:
            raise HTTPException(status_code=404, detail="repository is not connected")
        installation = await repo.get_installation(
            organization_id, connected_repository.installation_id
        )
        if installation is None or installation.provider == "github-local":
            yield IntegrationService(repo, {"github-local": local_adapter})
            return
        if installation.provider != "github" or installation.provider_configuration_id is None:
            raise HTTPException(status_code=409, detail="source-control provider is unavailable")
        configuration = await repo.get_source_control_configuration(
            installation.provider_configuration_id
        )
        if configuration is None or not configuration.enabled:
            raise HTTPException(status_code=409, detail="GitHub configuration is unavailable")
        secret_store = encrypted_secrets()
        private_reference = SecretReference(**configuration.private_key_reference)
        async with httpx.AsyncClient(
            base_url=configuration.api_base_url, timeout=30
        ) as github_client:
            app_client = GitHubAppClient(
                client=github_client, api_version=configuration.api_version
            )
            yield IntegrationService(
                repo,
                {
                    "github": GitHubSourceControl(
                        client=github_client,
                        credential_provider=GitHubInstallationCredentialProvider(
                            app_client=app_client,
                            app_id=configuration.app_id,
                            private_key_reference=private_reference,
                            secrets=secret_store,
                        ),
                        api_version=configuration.api_version,
                    )
                },
            )

    async def authorize(
        repo: PostgresIntegrationRepository,
        organization_id: UUID,
        subject: str,
        allowed: set[str],
    ) -> None:
        if await repo.role_for(organization_id, subject) not in allowed:
            raise HTTPException(status_code=403, detail="membership cannot perform this action")

    def require_platform_operator(principal: Principal) -> None:
        if not principal.is_platform_operator:
            raise HTTPException(status_code=403, detail="platform operator permission is required")

    def hash_state(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("select 1")
        return {"status": "ready"}

    @app.post(
        "/api/v1/platform/source-control-configurations/github/manifest",
        status_code=201,
    )
    async def start_github_manifest(
        payload: GitHubManifestStart,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> dict[str, Any]:
        require_platform_operator(principal)
        if any(item.enabled for item in await repo.list_source_control_configurations()):
            raise HTTPException(
                status_code=409,
                detail="an active source-control configuration already exists",
            )
        state = secrets.token_urlsafe(32)
        await repo.create_platform_setup_attempt(
            hash_state(state),
            principal.subject,
            datetime.now(UTC) + timedelta(minutes=10),
        )
        registration_base = (
            f"{resolved.github_web_url}/organizations/{quote(payload.owner)}/settings/apps/new"
            if payload.owner
            else f"{resolved.github_web_url}/settings/apps/new"
        )
        return {
            "registration_url": f"{registration_base}?state={quote(state)}",
            "state": state,
            "manifest": {
                "name": payload.display_name,
                "url": resolved.public_base_url,
                "redirect_url": (
                    f"{resolved.public_base_url}/app/admin/integrations/github/callback"
                    f"?state={quote(state)}"
                ),
                "callback_urls": [f"{resolved.public_base_url}/app/github/installations/callback"],
                "setup_url": f"{resolved.public_base_url}/app/github/installations/callback",
                "request_oauth_on_install": True,
                "public": True,
                "hook_attributes": {
                    "url": f"{resolved.public_base_url}/api/github/webhooks",
                    "active": payload.webhook_mode is WebhookMode.WEBHOOK,
                },
                "default_permissions": {
                    "contents": "write",
                    "pull_requests": "write",
                    "checks": "write",
                    "metadata": "read",
                },
                "default_events": [],
            },
        }

    @app.post(
        "/api/v1/platform/source-control-configurations/github/manifest/complete",
        status_code=201,
    )
    async def complete_github_manifest(
        payload: GitHubManifestComplete,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> Any:
        require_platform_operator(principal)
        if not await repo.consume_platform_setup_attempt(
            hash_state(payload.state), principal.subject, datetime.now(UTC)
        ):
            raise HTTPException(status_code=409, detail="setup state is invalid or expired")
        async with httpx.AsyncClient(
            base_url=resolved.github_api_url,
            timeout=30,
        ) as client:
            app_client = GitHubAppClient(client=client, api_version=resolved.github_api_version)
            try:
                conversion = await app_client.convert_manifest(payload.code)
            except httpx.HTTPError as error:
                raise HTTPException(
                    status_code=502, detail="GitHub manifest exchange failed"
                ) from error
        configuration_id = uuid4()
        namespace = f"github-app/{configuration_id}"
        private_key_reference = SecretReference(
            store="encrypted-file", namespace=namespace, key="private-key"
        )
        client_secret_reference = SecretReference(
            store="encrypted-file", namespace=namespace, key="client-secret"
        )
        webhook_secret_reference = SecretReference(
            store="encrypted-file", namespace=namespace, key="webhook-secret"
        )
        secret_store = encrypted_secrets()
        references_and_values = (
            (private_key_reference, conversion.pem),
            (client_secret_reference, conversion.client_secret),
            (webhook_secret_reference, conversion.webhook_secret),
        )
        try:
            for reference, value in references_and_values:
                await secret_store.put(reference, value)
            result = await use_case.configure_source_control(
                configuration_id=configuration_id,
                actor_subject=principal.subject,
                display_name=payload.display_name,
                provider="github",
                web_base_url=resolved.github_web_url,
                api_base_url=resolved.github_api_url,
                api_version=resolved.github_api_version,
                app_id=conversion.app_id,
                client_id=conversion.client_id,
                app_slug=conversion.app_slug,
                private_key_reference=private_key_reference,
                client_secret_reference=client_secret_reference,
                webhook_secret_reference=webhook_secret_reference,
                webhook_mode=payload.webhook_mode,
            )
            async with httpx.AsyncClient(
                base_url=resolved.github_api_url, timeout=30
            ) as health_client:
                health_adapter = GitHubAppClient(
                    client=health_client, api_version=resolved.github_api_version
                )
                await health_adapter.app(conversion.app_id, conversion.pem)
            await repo.update_source_control_configuration_health(configuration_id, "HEALTHY", True)
        except BaseException:
            for reference, _ in references_and_values:
                await secret_store.delete(reference)
            raise
        return jsonable_encoder(asdict(result))

    @app.get("/api/v1/platform/source-control-configurations")
    async def source_control_configurations(
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        require_platform_operator(principal)
        return jsonable_encoder(
            [asdict(item) for item in await repo.list_source_control_configurations()]
        )

    @app.post("/api/v1/platform/source-control-configurations/{configuration_id}/disable")
    async def disable_source_control_configuration(
        configuration_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> dict[str, str]:
        require_platform_operator(principal)
        configuration = await repo.get_source_control_configuration(configuration_id)
        if configuration is None:
            raise HTTPException(status_code=404, detail="configuration was not found")
        await repo.update_source_control_configuration_health(configuration_id, "DISABLED", False)
        await repo.record_platform_audit(
            actor_subject=principal.subject,
            action="source_control_configuration.disabled",
            target_type="source_control_configuration",
            target_id=configuration_id,
            details={"provider": configuration.provider},
        )
        return {"status": "disabled"}

    @app.post(
        "/api/v1/organizations/{organization_id}/github/installations",
        status_code=201,
    )
    async def start_github_installation(
        organization_id: UUID,
        payload: GitHubInstallationStart,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> dict[str, str]:
        await authorize(repo, organization_id, principal.subject, {"OWNER", "ADMIN"})
        configuration = await repo.get_source_control_configuration(payload.configuration_id)
        if not configuration or not configuration.enabled:
            raise HTTPException(status_code=404, detail="GitHub configuration is unavailable")
        state = secrets.token_urlsafe(32)
        await repo.create_connector_setup_attempt(
            organization_id,
            hash_state(state),
            principal.subject,
            configuration.id,
            datetime.now(UTC) + timedelta(minutes=10),
        )
        return {
            "installation_url": (
                f"{configuration.web_base_url}/apps/{quote(configuration.app_slug)}"
                f"/installations/new?state={quote(state)}"
            ),
            "state": state,
        }

    @app.get("/api/v1/organizations/{organization_id}/source-control-configurations")
    async def available_source_control_configurations(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, {"OWNER", "ADMIN"})
        configurations = await repo.list_source_control_configurations()
        return [
            {
                "id": str(item.id),
                "display_name": item.display_name,
                "provider": item.provider,
                "app_slug": item.app_slug,
                "webhook_mode": item.webhook_mode.value,
            }
            for item in configurations
            if item.enabled
        ]

    @app.post(
        "/api/v1/organizations/{organization_id}/github/installations/complete",
        status_code=201,
    )
    async def complete_github_installation(
        organization_id: UUID,
        payload: GitHubInstallationComplete,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, {"OWNER", "ADMIN"})
        configuration_id = await repo.consume_connector_setup_attempt(
            organization_id,
            hash_state(payload.state),
            principal.subject,
            datetime.now(UTC),
        )
        if configuration_id is None:
            raise HTTPException(status_code=409, detail="installation state is invalid or expired")
        configuration = await repo.get_source_control_configuration(configuration_id)
        if not configuration or not configuration.enabled:
            raise HTTPException(status_code=404, detail="GitHub configuration is unavailable")
        secret_store = encrypted_secrets()
        client_secret = await secret_store.get(
            SecretReference(**configuration.client_secret_reference)
        )
        async with httpx.AsyncClient(timeout=30) as oauth_client:
            token_response = await oauth_client.post(
                f"{configuration.web_base_url}/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": configuration.client_id,
                    "client_secret": client_secret.decode(),
                    "code": payload.code,
                },
            )
            if token_response.status_code >= 400:
                raise HTTPException(status_code=502, detail="GitHub OAuth exchange failed")
            user_token = str(token_response.json().get("access_token", ""))
        if not user_token:
            raise HTTPException(status_code=403, detail="GitHub user authorization failed")
        async with httpx.AsyncClient(
            base_url=configuration.api_base_url,
            timeout=30,
        ) as github_client:
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {user_token}",
                "X-GitHub-Api-Version": configuration.api_version,
            }
            visible = False
            for page in range(1, 11):
                response = await github_client.get(
                    "/user/installations",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                )
                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=502, detail="GitHub installation verification failed"
                    )
                installations = response.json().get("installations", [])
                if any(str(item["id"]) == payload.installation_id for item in installations):
                    visible = True
                    break
                if len(installations) < 100:
                    break
            if not visible:
                raise HTTPException(
                    status_code=403,
                    detail="GitHub installation is not accessible to the authorizing user",
                )
            app_client = GitHubAppClient(
                client=github_client, api_version=configuration.api_version
            )
            private_reference = SecretReference(**configuration.private_key_reference)
            installation_payload = await app_client.installation(
                payload.installation_id,
                configuration.app_id,
                await secret_store.get(private_reference),
            )
            adapter = GitHubSourceControl(
                client=github_client,
                credential_provider=GitHubInstallationCredentialProvider(
                    app_client=app_client,
                    app_id=configuration.app_id,
                    private_key_reference=private_reference,
                    secrets=secret_store,
                ),
            )
            github_service = IntegrationService(repo, {"github": adapter})
            account = installation_payload.get("account") or {}
            installation, repositories = await github_service.connect(
                organization_id=organization_id,
                actor_subject=principal.subject,
                provider="github",
                external_account_id=payload.installation_id,
                account_login=str(account.get("login", "unknown")),
                provider_configuration_id=configuration.id,
                granted_permissions=tuple(
                    f"{key}:{value}"
                    for key, value in dict(installation_payload.get("permissions") or {}).items()
                ),
                repository_selection=str(
                    installation_payload.get("repository_selection", "selected")
                ).upper(),
            )
        return jsonable_encoder(
            {
                "installation": asdict(installation),
                "repositories": [asdict(item) for item in repositories],
            }
        )

    @app.post("/api/v1/organizations/{organization_id}/connections", status_code=201)
    async def connect(
        organization_id: UUID,
        payload: ConnectionCreate,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> Any:
        await authorize(
            repo,
            organization_id,
            principal.subject,
            {"OWNER", "ADMIN"},
        )
        if payload.provider != "github-local":
            raise HTTPException(
                status_code=501,
                detail="real GitHub is not configured; select github-local explicitly",
            )
        installation, repositories = await use_case.connect(
            organization_id=organization_id,
            actor_subject=principal.subject,
            provider=payload.provider,
            external_account_id=payload.external_account_id,
            account_login=payload.account_login,
        )
        return jsonable_encoder(
            {
                "installation": asdict(installation),
                "repositories": [asdict(item) for item in repositories],
            }
        )

    @app.get("/api/v1/organizations/{organization_id}/repositories")
    async def repositories(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(
            repo,
            organization_id,
            principal.subject,
            {"OWNER", "ADMIN", "DEVELOPER", "REVIEWER"},
        )
        return jsonable_encoder(
            [asdict(item) for item in await repo.list_repositories(organization_id)]
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/repositories/{repository_id}/pull-requests",
        status_code=201,
    )
    async def create_pull_request(
        organization_id: UUID,
        repository_id: UUID,
        payload: PullRequestCreate,
        principal: PrincipalDependency,
        repo: Repo,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> Any:
        await authorize(
            repo,
            organization_id,
            principal.subject,
            {"OWNER", "ADMIN", "DEVELOPER"},
        )
        async with service_for_repository(repo, organization_id, repository_id) as use_case:
            result = await use_case.create_pull_request(
                organization_id=organization_id,
                actor_subject=principal.subject,
                repository_id=repository_id,
                title=payload.title,
                body=payload.body,
                head_branch=payload.head_branch,
                head_sha=payload.head_sha,
                idempotency_key=idempotency_key,
            )
        return jsonable_encoder(asdict(result))

    @app.post("/webhooks/github", status_code=202)
    async def github_webhook(
        request: Request,
        repo: Repo,
        x_github_delivery: Annotated[str, Header(alias="X-GitHub-Delivery")],
        x_github_event: Annotated[str, Header(alias="X-GitHub-Event")],
        x_hub_signature_256: Annotated[str, Header(alias="X-Hub-Signature-256")],
        x_github_hook_installation_target_id: Annotated[
            str | None, Header(alias="X-GitHub-Hook-Installation-Target-ID")
        ] = None,
    ) -> dict[str, str]:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 2_097_152:
                    raise HTTPException(status_code=413, detail="webhook payload is too large")
            except ValueError as error:
                raise HTTPException(status_code=400, detail="content length is invalid") from error
        body = await request.body()
        if len(body) > 2_097_152:
            raise HTTPException(status_code=413, detail="webhook payload is too large")
        if x_github_hook_installation_target_id:
            configuration = await repo.source_control_configuration_for_app_id(
                "github", x_github_hook_installation_target_id
            )
            if not configuration or not configuration.enabled:
                raise HTTPException(status_code=404, detail="GitHub App is not configured")
            secret = await encrypted_secrets().get(
                SecretReference(**configuration.webhook_secret_reference)
            )
        elif resolved.github_webhook_secret_file:
            secret = (
                await asyncio.to_thread(Path(resolved.github_webhook_secret_file).read_bytes)
            ).strip()
        else:
            raise HTTPException(status_code=503, detail="GitHub webhook adapter is disabled")
        if not verify_webhook_signature(
            body=body, signature_header=x_hub_signature_256, secret=secret
        ):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        try:
            payload = json.loads(body)
            external_installation_id = str(payload["installation"]["id"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=422, detail="webhook has no installation identity"
            ) from error
        organization_id = await repo.organization_for_external_installation(
            "github", external_installation_id
        )
        if organization_id is None:
            raise HTTPException(status_code=404, detail="installation is not connected")
        accepted = await repo.record_webhook_delivery(
            provider="github",
            delivery_id=x_github_delivery,
            organization_id=organization_id,
            event_name=x_github_event,
            payload_hash=hashlib.sha256(body).hexdigest(),
        )
        if accepted and x_github_event == "installation":
            installation = await repo.installation_for_external(
                organization_id, "github", external_installation_id
            )
            if installation:
                action = str(payload.get("action", ""))
                if action == "deleted":
                    installation.disconnect()
                elif action == "suspend":
                    installation.suspend()
                elif action == "unsuspend":
                    installation.activate()
                await repo.update_installation(installation)
                await repo.record_audit(
                    organization_id=organization_id,
                    actor_subject="github-webhook",
                    action=f"connector.installation.{action or 'received'}",
                    target_type="connector_installation",
                    target_id=installation.id,
                    details={"delivery_id": x_github_delivery},
                )
        return {"status": "accepted" if accepted else "duplicate"}

    @app.post("/internal/v1/pull-requests", status_code=201)
    async def internal_pull_request(
        payload: InternalPullRequestCreate,
        repo: Repo,
        x_internal_service_token: Annotated[str, Header(alias="X-Internal-Service-Token")],
    ) -> Any:
        if not hmac.compare_digest(x_internal_service_token, resolved.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid service identity")
        async with service_for_repository(
            repo, payload.organization_id, payload.repository_id
        ) as use_case:
            result = await use_case.create_pull_request(
                organization_id=payload.organization_id,
                actor_subject="delivery-service",
                repository_id=payload.repository_id,
                title=payload.title,
                body=payload.body,
                head_branch=payload.head_branch,
                head_sha=payload.head_sha,
                idempotency_key=payload.idempotency_key,
            )
        return jsonable_encoder(asdict(result))

    @app.post("/internal/v1/source-credentials/exchange")
    async def exchange_source_credential(
        payload: SourceCredentialExchange,
        repo: Repo,
    ) -> dict[str, str]:
        try:
            claims = jwt.decode(
                payload.capability,
                resolved.internal_service_token,
                algorithms=["HS256"],
                audience="mvp-integrations-source",
                issuer="mvp-delivery",
                options={
                    "require": [
                        "exp",
                        "iat",
                        "jti",
                        "organization_id",
                        "repository_id",
                        "purpose",
                    ]
                },
            )
            organization_id = UUID(str(claims["organization_id"]))
            repository_id = UUID(str(claims["repository_id"]))
            expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=401, detail="source capability is invalid") from error
        purpose = str(claims["purpose"])
        if purpose not in {"CHECKOUT_READ", "PUBLISH_WRITE"}:
            raise HTTPException(status_code=401, detail="source capability purpose is invalid")
        if not await repo.redeem_source_capability(organization_id, str(claims["jti"]), expires_at):
            raise HTTPException(status_code=409, detail="source capability was already redeemed")
        connected_repository = await repo.get_repository(organization_id, repository_id)
        if (
            connected_repository is None
            or connected_repository.access_status is not RepositoryAccessStatus.ACTIVE
        ):
            raise HTTPException(status_code=403, detail="repository access is not active")
        installation = await repo.get_installation(
            organization_id, connected_repository.installation_id
        )
        if (
            installation is not None
            and installation.provider == "github-local"
            and connected_repository.is_development_substitute
        ):
            return {
                "clone_locator": connected_repository.clone_locator,
                "default_branch": connected_repository.default_branch,
                "username": "",
                "token": "",
                "expires_at": "",
                "development_substitute": "true",
            }
        if (
            installation is None
            or installation.status is not InstallationStatus.ACTIVE
            or installation.provider_configuration_id is None
        ):
            raise HTTPException(status_code=403, detail="connector installation is not active")
        configuration = await repo.get_source_control_configuration(
            installation.provider_configuration_id
        )
        if configuration is None or not configuration.enabled:
            raise HTTPException(status_code=403, detail="GitHub configuration is not active")
        secret_store = encrypted_secrets()
        async with httpx.AsyncClient(
            base_url=configuration.api_base_url, timeout=30
        ) as github_client:
            app_client = GitHubAppClient(
                client=github_client, api_version=configuration.api_version
            )
            credential = await app_client.installation_token(
                installation_id=installation.external_account_id,
                app_id=configuration.app_id,
                private_key=await secret_store.get(
                    SecretReference(**configuration.private_key_reference)
                ),
                repository_id=connected_repository.external_repository_id,
                permissions={"contents": "read" if purpose == "CHECKOUT_READ" else "write"},
            )
        return {
            "clone_locator": connected_repository.clone_locator,
            "default_branch": connected_repository.default_branch,
            "username": "x-access-token",
            "token": credential.token,
            "expires_at": credential.expires_at or "",
        }

    return app


app = create_app()
