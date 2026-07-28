import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from mvp_common.contracts import SecretReference
from mvp_common.logging import configure_logging
from mvp_observability import configure_observability
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mvp_delivery.adapters.oidc import Principal, PrincipalProvider
from mvp_delivery.adapters.postgres import (
    PostgresDeliveryRepository,
    PostgresWorkflowGateway,
)
from mvp_delivery.application.service import DeliveryService
from mvp_delivery.domain.agent_runtimes import AGENT_CATALOG
from mvp_delivery.domain.errors import UnsupportedProviderConfiguration
from mvp_delivery.domain.models import AuthenticationMode, ExecutionBudget, ExecutionStatus
from mvp_delivery.settings import Settings

MANAGEMENT_ROLES = {"OWNER", "ADMIN"}
EXECUTION_ROLES = {"OWNER", "ADMIN", "DEVELOPER", "REVIEWER"}
REVIEW_ROLES = {"OWNER", "ADMIN", "REVIEWER"}
TERMINAL_STATUSES = {
    ExecutionStatus.DELIVERED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
}


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SecretReferenceRequest(RequestModel):
    store: str = Field(min_length=1, max_length=64)
    namespace: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=256)
    version: str | None = Field(default=None, max_length=128)


class ProviderConfigurationCreate(RequestModel):
    display_name: str = Field(min_length=2, max_length=200)
    provider: str = Field(min_length=1, max_length=64)
    runtime: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    authentication_mode: AuthenticationMode
    secret_reference: SecretReferenceRequest | None = None
    is_development_substitute: bool = False


class RunnerPoolCreate(RequestModel):
    name: str = Field(min_length=2, max_length=200)
    runner_type: str = Field(pattern=r"^(LOCAL|CUSTOMER_HOSTED|PLATFORM_MANAGED)$")


class RunnerEnrollmentCreate(RequestModel):
    pool_id: UUID


class RunnerEnroll(RequestModel):
    enrollment_token: str = Field(min_length=32, max_length=256)
    name: str = Field(min_length=2, max_length=200)
    capabilities: tuple[str, ...] = Field(min_length=1, max_length=100)


class BudgetRequest(RequestModel):
    max_duration_seconds: int = Field(ge=30, le=86400)
    max_attempts: int = Field(ge=1, le=10)
    max_turns: int = Field(ge=1, le=100)
    max_cost_minor: int = Field(ge=0, le=10_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ReadyWorkItem(RequestModel):
    project_id: UUID
    work_item_id: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10000)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1, max_length=100)
    repository_connection_id: UUID
    provider_configuration_id: UUID
    runner_pool_id: UUID
    budget: BudgetRequest
    correlation_id: UUID


class AgentEventReport(RequestModel):
    sequence: int = Field(ge=1)
    kind: str = Field(pattern=r"^(PLAN|TOOL|COMMAND|RESULT|ERROR|APPROVAL|USAGE)$")
    name: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class AgentReport(RequestModel):
    success: bool
    summary: str = Field(max_length=4000)
    turns: int = Field(ge=0, le=10000)
    changed_paths: tuple[str, ...] = Field(max_length=10000)
    events: tuple[AgentEventReport, ...] = Field(max_length=10000)
    session_id: str | None = Field(default=None, max_length=200)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ValidationEvidenceReport(RequestModel):
    executable: str = Field(min_length=1, max_length=512)
    arguments: tuple[str, ...] = Field(max_length=100)
    exit_code: int
    stdout: str = Field(max_length=65536)
    stderr: str = Field(max_length=65536)
    duration_ms: int = Field(ge=0)


class ValidationReport(RequestModel):
    passed: bool
    validator_image: str = Field(min_length=1, max_length=512)
    evidence: tuple[ValidationEvidenceReport, ...] = Field(max_length=100)


class RunnerJobComplete(RequestModel):
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    patch: str = Field(max_length=131072)
    duration_seconds: int = Field(ge=0)
    cost_minor: int = Field(ge=0)
    agent: AgentReport
    validation: ValidationReport


class ProviderVerificationCreate(RequestModel):
    runner_pool_id: UUID


class ProviderVerificationComplete(RequestModel):
    success: bool
    summary: str = Field(max_length=1000)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    configure_logging()
    engine = create_async_engine(resolved.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    principals = PrincipalProvider(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(
        title="MVP Master Delivery",
        version="1.0.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    configure_observability(app, engine, service_name=resolved.service_name)

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    Session = Annotated[AsyncSession, Depends(session_dependency)]
    PrincipalDependency = Annotated[Principal, Depends(principals.authenticate)]

    def repository(session: Session) -> PostgresDeliveryRepository:
        return PostgresDeliveryRepository(session)

    Repo = Annotated[PostgresDeliveryRepository, Depends(repository)]

    def service(session: Session, repo: Repo) -> DeliveryService:
        return DeliveryService(repo, PostgresWorkflowGateway(session))

    Service = Annotated[DeliveryService, Depends(service)]

    async def authorize(
        repo: PostgresDeliveryRepository,
        organization_id: UUID,
        subject: str,
        allowed: set[str],
    ) -> None:
        role = await repo.role_for(organization_id, subject)
        if role not in allowed:
            raise HTTPException(status_code=403, detail="membership cannot perform this action")

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("select 1")
        return {"status": "ready"}

    @app.post(
        "/api/v1/organizations/{organization_id}/provider-configurations",
        status_code=201,
    )
    async def create_provider_configuration(
        organization_id: UUID,
        payload: ProviderConfigurationCreate,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, MANAGEMENT_ROLES)
        reference = (
            SecretReference(**payload.secret_reference.model_dump())
            if payload.secret_reference
            else None
        )
        if reference and (
            reference.store != "encrypted-file"
            or reference.namespace != f"model-credentials/{organization_id}"
        ):
            raise HTTPException(
                status_code=422,
                detail="secret reference is not owned by this organization",
            )
        try:
            result = await use_case.create_provider_configuration(
                organization_id=organization_id,
                actor_subject=principal.subject,
                display_name=payload.display_name,
                provider=payload.provider,
                runtime=payload.runtime,
                model=payload.model,
                authentication_mode=payload.authentication_mode,
                secret_reference=reference,
                is_development_substitute=payload.is_development_substitute,
            )
        except (UnsupportedProviderConfiguration, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return jsonable_encoder(asdict(result))

    @app.get("/api/v1/organizations/{organization_id}/provider-configurations")
    async def provider_configurations(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        result: list[dict[str, Any]] = []
        for item in await repo.list_provider_configurations(organization_id):
            document = asdict(item)
            latest = await repo.latest_provider_verification(organization_id, item.id)
            document["verification_status"] = latest.status if latest else "NOT_VERIFIED"
            document["verification_id"] = str(latest.id) if latest else None
            result.append(document)
        return jsonable_encoder(result)

    @app.get("/api/v1/organizations/{organization_id}/agent-catalog")
    async def agent_catalog(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        return jsonable_encoder(
            [
                {
                    **asdict(entry),
                    "authentication_mode": "API_KEY_REFERENCE",
                    "is_development_substitute": False,
                }
                for entry in AGENT_CATALOG
            ]
        )

    def verification_document(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "provider_configuration_id": str(row.provider_configuration_id),
            "runner_pool_id": str(row.pool_id),
            "status": row.status,
            "result": row.result,
            "created_at": row.created_at.isoformat(),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    @app.post(
        "/api/v1/organizations/{organization_id}/provider-configurations/"
        "{configuration_id}/verifications",
        status_code=202,
    )
    async def create_provider_verification(
        organization_id: UUID,
        configuration_id: UUID,
        payload: ProviderVerificationCreate,
        principal: PrincipalDependency,
        repo: Repo,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, MANAGEMENT_ROLES)
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key is required")
        configuration = await repo.get_provider_configuration(organization_id, configuration_id)
        if configuration is None or not configuration.enabled:
            raise HTTPException(status_code=404, detail="provider configuration was not found")
        pools = await repo.list_runner_pools(organization_id)
        pool = next(
            (item for item in pools if item["id"] == str(payload.runner_pool_id)),
            None,
        )
        if pool is None:
            raise HTTPException(status_code=404, detail="runner pool was not found")
        raw_capabilities = pool.get("capabilities", [])
        capabilities = (
            {str(item) for item in raw_capabilities}
            if isinstance(raw_capabilities, list)
            else set()
        )
        if configuration.runtime not in capabilities:
            raise HTTPException(
                status_code=409,
                detail=f"runner pool does not advertise runtime {configuration.runtime!r}",
            )
        row = await repo.create_provider_verification(
            verification_id=uuid4(),
            organization_id=organization_id,
            provider_configuration_id=configuration_id,
            pool_id=payload.runner_pool_id,
            idempotency_key=idempotency_key,
        )
        await repo.record_audit(
            organization_id=organization_id,
            actor_subject=principal.subject,
            action="provider_configuration.verification_requested",
            target_id=row.id,
            details={
                "provider_configuration_id": str(configuration_id),
                "runner_pool_id": str(payload.runner_pool_id),
            },
        )
        return verification_document(row)

    @app.get(
        "/api/v1/organizations/{organization_id}/provider-configurations/"
        "{configuration_id}/verifications/latest"
    )
    async def latest_provider_verification(
        organization_id: UUID,
        configuration_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        row = await repo.latest_provider_verification(organization_id, configuration_id)
        if row is None:
            raise HTTPException(status_code=404, detail="provider has not been verified")
        return verification_document(row)

    @app.post("/api/v1/organizations/{organization_id}/runner-pools", status_code=201)
    async def create_runner_pool(
        organization_id: UUID,
        payload: RunnerPoolCreate,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> dict[str, str]:
        await authorize(repo, organization_id, principal.subject, MANAGEMENT_ROLES)
        pool_id = uuid4()
        await repo.add_runner_pool(organization_id, pool_id, payload.name, payload.runner_type)
        return {"id": str(pool_id), "name": payload.name, "runner_type": payload.runner_type}

    @app.get("/api/v1/organizations/{organization_id}/runner-pools")
    async def runner_pools(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        return await repo.list_runner_pools(organization_id)

    @app.post(
        "/api/v1/organizations/{organization_id}/runner-enrollments",
        status_code=201,
    )
    async def create_runner_enrollment(
        organization_id: UUID,
        payload: RunnerEnrollmentCreate,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> dict[str, str]:
        await authorize(repo, organization_id, principal.subject, MANAGEMENT_ROLES)
        token = await use_case.create_runner_enrollment(
            organization_id=organization_id,
            actor_subject=principal.subject,
            pool_id=payload.pool_id,
        )
        return {"enrollment_token": token, "expires_in_seconds": "600"}

    @app.post("/runner/v1/enroll", status_code=201)
    async def enroll_runner(payload: RunnerEnroll, use_case: Service) -> dict[str, str]:
        runner, credential = await use_case.enroll_runner(
            enrollment_token=payload.enrollment_token,
            name=payload.name,
            capabilities=payload.capabilities,
        )
        return {
            "runner_id": str(runner.id),
            "organization_id": str(runner.organization_id),
            "runner_credential": credential,
        }

    async def authenticated_runner(
        repo: PostgresDeliveryRepository,
        authorization: str | None,
        runner_id_header: str | None,
    ) -> Any:
        if not authorization or not authorization.startswith("Runner ") or not runner_id_header:
            raise HTTPException(status_code=401, detail="runner identity is required")
        try:
            runner_id = UUID(runner_id_header)
        except ValueError as error:
            raise HTTPException(status_code=401, detail="runner identity is invalid") from error
        runner = await repo.authenticate_runner(
            runner_id, authorization.removeprefix("Runner ").strip()
        )
        if runner is None:
            raise HTTPException(status_code=401, detail="runner identity is invalid")
        return runner

    @app.post("/runner/v1/jobs/lease")
    async def lease_runner_job(
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> Any:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        job = await repo.lease_runner_job(runner)
        if job is None:
            return Response(status_code=204)
        return {
            "job_id": str(job.id),
            "execution_id": str(job.execution_id),
            "organization_id": str(job.organization_id),
            **job.payload,
        }

    @app.post("/runner/v1/provider-verifications/lease")
    async def lease_provider_verification(
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> Any:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        verification = await repo.lease_provider_verification(runner)
        if verification is None:
            return Response(status_code=204)
        configuration = await repo.get_provider_configuration(
            verification.organization_id, verification.provider_configuration_id
        )
        if configuration is None:
            verification.status = "FAILED"
            verification.result = {
                "success": False,
                "summary": "Provider configuration is unavailable.",
            }
            verification.completed_at = datetime.now(UTC)
            return Response(status_code=204)
        return {
            "verification_id": str(verification.id),
            "organization_id": str(verification.organization_id),
            "provider_configuration_id": str(configuration.id),
            "provider": configuration.provider,
            "runtime": configuration.runtime,
            "model": configuration.model,
            "authentication_mode": configuration.authentication_mode.value,
            "secret_reference": (
                configuration.secret_reference.model_dump()
                if configuration.secret_reference
                else None
            ),
            "max_turns": 1,
            "max_duration_seconds": 120,
        }

    @app.post("/runner/v1/provider-verifications/{verification_id}/heartbeat")
    async def heartbeat_provider_verification(
        verification_id: UUID,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        row = await repo.heartbeat_provider_verification(runner, verification_id)
        if row is None:
            raise HTTPException(status_code=409, detail="verification lease is not active")
        return {"status": "extended"}

    @app.post("/runner/v1/provider-verifications/{verification_id}/complete")
    async def complete_provider_verification(
        verification_id: UUID,
        payload: ProviderVerificationComplete,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        row = await repo.complete_provider_verification(
            runner, verification_id, payload.model_dump(mode="json")
        )
        if row is None:
            raise HTTPException(status_code=409, detail="verification lease is not active")
        await repo.record_audit(
            organization_id=row.organization_id,
            actor_subject=f"runner:{runner.id}",
            action=f"provider_configuration.verification_{row.status.lower()}",
            target_id=row.id,
            details={"provider_configuration_id": str(row.provider_configuration_id)},
        )
        return {"status": row.status}

    @app.post("/runner/v1/provider-verifications/{verification_id}/model-capability")
    async def provider_verification_model_capability(
        verification_id: UUID,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        verification = await repo.heartbeat_provider_verification(runner, verification_id)
        if verification is None:
            raise HTTPException(status_code=409, detail="verification lease is not active")
        configuration = await repo.get_provider_configuration(
            verification.organization_id, verification.provider_configuration_id
        )
        if configuration is None or configuration.secret_reference is None:
            raise HTTPException(status_code=409, detail="verification has no secret reference")
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "mvp-delivery",
                "aud": "mvp-integrations-model",
                "iat": now,
                "exp": now + 60,
                "jti": str(uuid4()),
                "organization_id": str(verification.organization_id),
                "execution_id": str(verification.id),
                "job_id": str(verification.id),
                "runner_id": str(runner.id),
                "secret_reference": configuration.secret_reference.model_dump(),
                "purpose": "MODEL_CREDENTIAL_READ",
            },
            resolved.internal_service_token,
            algorithm="HS256",
        )
        return {"capability": str(token), "expires_in_seconds": "60"}

    @app.post("/runner/v1/jobs/{job_id}/complete")
    async def complete_runner_job(
        job_id: UUID,
        payload: RunnerJobComplete,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        completed = await repo.complete_runner_job(runner, job_id, payload.model_dump(mode="json"))
        if completed is None:
            raise HTTPException(status_code=409, detail="job lease is not active for runner")
        return {"status": "accepted"}

    @app.post("/runner/v1/jobs/{job_id}/heartbeat")
    async def heartbeat_runner_job(
        job_id: UUID,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        heartbeat = await repo.heartbeat_runner_job(runner, job_id)
        if heartbeat is None:
            raise HTTPException(status_code=409, detail="job lease is not active for runner")
        return {"status": "extended"}

    @app.post("/runner/v1/jobs/{job_id}/source-capability")
    async def source_capability(
        job_id: UUID,
        purpose: Annotated[str, Header(alias="X-Source-Purpose")],
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        if purpose not in {"CHECKOUT_READ", "PUBLISH_WRITE"}:
            raise HTTPException(status_code=422, detail="source purpose is invalid")
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        job = await repo.heartbeat_runner_job(runner, job_id)
        if job is None:
            raise HTTPException(status_code=409, detail="job lease is not active for runner")
        repository_id = str(job.payload.get("repository_connection_id", ""))
        if not repository_id:
            raise HTTPException(status_code=409, detail="job has no connected repository")
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "mvp-delivery",
                "aud": "mvp-integrations-source",
                "iat": now,
                "exp": now + 120,
                "jti": str(uuid4()),
                "organization_id": str(job.organization_id),
                "execution_id": str(job.execution_id),
                "job_id": str(job.id),
                "runner_id": str(runner.id),
                "repository_id": repository_id,
                "purpose": purpose,
            },
            resolved.internal_service_token,
            algorithm="HS256",
        )
        return {"capability": str(token), "expires_in_seconds": "120"}

    @app.post("/runner/v1/jobs/{job_id}/model-capability")
    async def model_capability(
        job_id: UUID,
        repo: Repo,
        authorization: Annotated[str | None, Header()] = None,
        x_runner_id: Annotated[str | None, Header(alias="X-Runner-ID")] = None,
    ) -> dict[str, str]:
        """Mint a short-lived, single-use capability the leased runner redeems
        against integrations' `/internal/v1/model-credentials/exchange` for the
        plaintext value of the job's model API key. Mirrors `source_capability`
        above; a distinct JWT audience (`mvp-integrations-model`) keeps a model
        capability from ever being redeemable as a source capability or vice
        versa. A job whose `authentication_mode` is not `API_KEY_REFERENCE`, or
        that has no `secret_reference`, has nothing to mint a capability for.
        """
        runner = await authenticated_runner(repo, authorization, x_runner_id)
        job = await repo.heartbeat_runner_job(runner, job_id)
        if job is None:
            raise HTTPException(status_code=409, detail="job lease is not active for runner")
        if job.payload.get("authentication_mode") != "API_KEY_REFERENCE":
            raise HTTPException(
                status_code=409, detail="job does not use API_KEY_REFERENCE authentication"
            )
        secret_reference = job.payload.get("secret_reference")
        if not secret_reference:
            raise HTTPException(status_code=409, detail="job has no secret reference")
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "mvp-delivery",
                "aud": "mvp-integrations-model",
                "iat": now,
                "exp": now + 60,
                "jti": str(uuid4()),
                "organization_id": str(job.organization_id),
                "execution_id": str(job.execution_id),
                "job_id": str(job.id),
                "runner_id": str(runner.id),
                "secret_reference": secret_reference,
                "purpose": "MODEL_CREDENTIAL_READ",
            },
            resolved.internal_service_token,
            algorithm="HS256",
        )
        return {"capability": str(token), "expires_in_seconds": "60"}

    @app.post("/api/v1/organizations/{organization_id}/executions", status_code=202)
    async def accept_ready_work_item(
        organization_id: UUID,
        payload: ReadyWorkItem,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Any:
        del idempotency_key
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        result = await use_case.accept_ready_work_item(
            organization_id=organization_id,
            project_id=payload.project_id,
            work_item_id=payload.work_item_id,
            title=payload.title,
            description=payload.description,
            acceptance_criteria=payload.acceptance_criteria,
            repository_connection_id=payload.repository_connection_id,
            provider_configuration_id=payload.provider_configuration_id,
            runner_pool_id=payload.runner_pool_id,
            budget=ExecutionBudget(**payload.budget.model_dump()),
            correlation_id=payload.correlation_id,
        )
        return jsonable_encoder(asdict(result))

    @app.get("/api/v1/organizations/{organization_id}/executions")
    async def list_executions(
        organization_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        return jsonable_encoder(
            [asdict(item) for item in await repo.list_executions(organization_id)]
        )

    @app.post("/api/v1/organizations/{organization_id}/executions/{execution_id}/approve")
    async def approve_execution(
        organization_id: UUID,
        execution_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, REVIEW_ROLES)
        return jsonable_encoder(
            asdict(
                await use_case.approve_execution(
                    organization_id=organization_id,
                    execution_id=execution_id,
                    actor_subject=principal.subject,
                )
            )
        )

    @app.post("/api/v1/organizations/{organization_id}/executions/{execution_id}/cancel")
    async def cancel_execution(
        organization_id: UUID,
        execution_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
        use_case: Service,
    ) -> Any:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        return jsonable_encoder(
            asdict(
                await use_case.cancel_execution(
                    organization_id=organization_id,
                    execution_id=execution_id,
                    actor_subject=principal.subject,
                )
            )
        )

    @app.get("/api/v1/organizations/{organization_id}/executions/{execution_id}/events")
    async def execution_events(
        organization_id: UUID,
        execution_id: UUID,
        principal: PrincipalDependency,
        repo: Repo,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        await authorize(repo, organization_id, principal.subject, EXECUTION_ROLES)
        after = int(last_event_id or "0")

        async def stream() -> AsyncIterator[str]:
            current = after
            idle_cycles = 0
            while idle_cycles < 300:
                async with sessions() as stream_session:
                    stream_repo = PostgresDeliveryRepository(stream_session)
                    events = await stream_repo.list_events(organization_id, execution_id, current)
                    execution = await stream_repo.get_execution(organization_id, execution_id)
                for event in events:
                    current = event.sequence
                    yield (
                        f"id: {event.sequence}\n"
                        f"data: {json.dumps(jsonable_encoder(asdict(event)))}\n\n"
                    )
                if events:
                    idle_cycles = 0
                else:
                    idle_cycles += 1
                    yield ": keep-alive\n\n"
                if execution and execution.status in TERMINAL_STATUSES and not events:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
