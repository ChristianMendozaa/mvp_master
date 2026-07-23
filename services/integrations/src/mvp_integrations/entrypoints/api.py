import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from mvp_common.logging import configure_logging
from mvp_observability import configure_observability
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mvp_integrations.adapters.github import verify_webhook_signature
from mvp_integrations.adapters.local_source_control import LocalSourceControl
from mvp_integrations.adapters.oidc import Principal, PrincipalProvider
from mvp_integrations.adapters.postgres import PostgresIntegrationRepository
from mvp_integrations.application.service import IntegrationService
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


class InternalPullRequestCreate(PullRequestCreate):
    organization_id: UUID
    repository_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=256)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    configure_logging()
    engine = create_async_engine(resolved.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    principals = PrincipalProvider(resolved)
    local_adapter = LocalSourceControl()

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

    async def authorize(
        repo: PostgresIntegrationRepository,
        organization_id: UUID,
        subject: str,
        allowed: set[str],
    ) -> None:
        if await repo.role_for(organization_id, subject) not in allowed:
            raise HTTPException(status_code=403, detail="membership cannot perform this action")

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("select 1")
        return {"status": "ready"}

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
        use_case: Service,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> Any:
        await authorize(
            repo,
            organization_id,
            principal.subject,
            {"OWNER", "ADMIN", "DEVELOPER"},
        )
        result = await use_case.create_pull_request(
            organization_id=organization_id,
            actor_subject=principal.subject,
            repository_id=repository_id,
            title=payload.title,
            body=payload.body,
            head_branch=payload.head_branch,
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
    ) -> dict[str, str]:
        if not resolved.github_webhook_secret_file:
            raise HTTPException(status_code=503, detail="GitHub webhook adapter is disabled")
        body = await request.body()
        secret = (
            await asyncio.to_thread(Path(resolved.github_webhook_secret_file).read_bytes)
        ).strip()
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
        return {"status": "accepted" if accepted else "duplicate"}

    @app.post("/internal/v1/pull-requests", status_code=201)
    async def internal_pull_request(
        payload: InternalPullRequestCreate,
        use_case: Service,
        x_internal_service_token: Annotated[str, Header(alias="X-Internal-Service-Token")],
    ) -> Any:
        if not hmac.compare_digest(x_internal_service_token, resolved.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid service identity")
        result = await use_case.create_pull_request(
            organization_id=payload.organization_id,
            actor_subject="delivery-service",
            repository_id=payload.repository_id,
            title=payload.title,
            body=payload.body,
            head_branch=payload.head_branch,
            idempotency_key=payload.idempotency_key,
        )
        return jsonable_encoder(asdict(result))

    return app


app = create_app()
