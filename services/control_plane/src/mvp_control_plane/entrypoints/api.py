from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from mvp_common.logging import configure_logging
from mvp_observability import configure_observability
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from mvp_control_plane.adapters.oidc import Principal, PrincipalProvider
from mvp_control_plane.adapters.postgres import PostgresUnitOfWork
from mvp_control_plane.application.service import ControlPlaneService
from mvp_control_plane.domain.errors import Conflict, DomainError, NotFound, PermissionDenied
from mvp_control_plane.domain.models import Budget
from mvp_control_plane.settings import Settings


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrganizationCreate(RequestModel):
    name: str = Field(min_length=2, max_length=200)


class ProjectCreate(RequestModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=1, max_length=4000)


class IntakeCreate(RequestModel):
    project_id: UUID
    client_id: UUID | None = None
    problem: str = Field(min_length=10, max_length=10000)
    intended_users: str = Field(min_length=2, max_length=4000)
    required_functionality: tuple[str, ...] = Field(min_length=1, max_length=100)
    exclusions: tuple[str, ...] = Field(default=(), max_length=100)
    constraints: tuple[str, ...] = Field(default=(), max_length=100)


class SpecificationDraft(RequestModel):
    title: str = Field(min_length=2, max_length=300)


class ApprovalDecision(RequestModel):
    reason: str | None = Field(default=None, max_length=4000)


class BudgetRequest(RequestModel):
    max_duration_seconds: int = Field(ge=30, le=86400)
    max_attempts: int = Field(ge=1, le=10)
    max_turns: int = Field(ge=1, le=100)
    max_cost_minor: int = Field(ge=0, le=10_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class WorkItemReady(RequestModel):
    repository_connection_id: UUID
    provider_configuration_id: UUID
    runner_pool_id: UUID
    budget: BudgetRequest


def correlation_id(x_correlation_id: str | None = Header(default=None)) -> UUID:
    if x_correlation_id:
        try:
            return UUID(x_correlation_id)
        except ValueError:
            pass
    return uuid4()


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
        title="MVP Master Control Plane",
        version="1.0.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    configure_observability(app, engine, service_name=resolved.service_name)
    app.state.engine = engine

    def service() -> ControlPlaneService:
        return ControlPlaneService(PostgresUnitOfWork(sessions))

    PrincipalDependency = Annotated[Principal, Depends(principals.authenticate)]
    ServiceDependency = Annotated[ControlPlaneService, Depends(service)]
    CorrelationDependency = Annotated[UUID, Depends(correlation_id)]

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError) -> JSONResponse:
        statuses: dict[type[DomainError], int] = {
            PermissionDenied: 403,
            NotFound: 404,
            Conflict: 409,
        }
        return JSONResponse(
            status_code=statuses.get(type(error), 422),
            content={"error": {"code": error.code, "message": str(error)}},
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, str]:
        database: AsyncEngine = request.app.state.engine
        async with database.connect() as connection:
            await connection.exec_driver_sql("select 1")
        return {"status": "ready"}

    @app.post("/api/v1/organizations", status_code=201)
    async def create_organization(
        payload: OrganizationCreate,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        result = await use_case.create_organization(
            actor_subject=principal.subject,
            name=payload.name,
            correlation_id=correlation,
        )
        return jsonable_encoder(asdict(result))

    @app.get("/api/v1/organizations")
    async def list_organizations(
        principal: PrincipalDependency,
        use_case: ServiceDependency,
    ) -> Any:
        return jsonable_encoder(
            [
                {"organization": asdict(organization), "role": role}
                for organization, role in await use_case.organizations_for(
                    actor_subject=principal.subject
                )
            ]
        )

    @app.get("/api/v1/organizations/{organization_id}/dashboard")
    async def dashboard(
        organization_id: UUID,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
    ) -> Any:
        return jsonable_encoder(
            await use_case.dashboard(
                actor_subject=principal.subject, organization_id=organization_id
            )
        )

    @app.post("/api/v1/organizations/{organization_id}/projects", status_code=201)
    async def create_project(
        organization_id: UUID,
        payload: ProjectCreate,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        return jsonable_encoder(
            asdict(
                await use_case.create_project(
                    actor_subject=principal.subject,
                    organization_id=organization_id,
                    name=payload.name,
                    description=payload.description,
                    correlation_id=correlation,
                )
            )
        )

    @app.post("/api/v1/organizations/{organization_id}/intakes", status_code=201)
    async def create_intake(
        organization_id: UUID,
        payload: IntakeCreate,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        return jsonable_encoder(
            asdict(
                await use_case.submit_intake(
                    actor_subject=principal.subject,
                    organization_id=organization_id,
                    project_id=payload.project_id,
                    client_id=payload.client_id,
                    problem=payload.problem,
                    intended_users=payload.intended_users,
                    required_functionality=payload.required_functionality,
                    exclusions=payload.exclusions,
                    constraints=payload.constraints,
                    correlation_id=correlation,
                )
            )
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/intakes/{intake_id}/specifications",
        status_code=201,
    )
    async def draft_specification(
        organization_id: UUID,
        intake_id: UUID,
        payload: SpecificationDraft,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        specification, version = await use_case.draft_specification(
            actor_subject=principal.subject,
            organization_id=organization_id,
            intake_id=intake_id,
            title=payload.title,
            correlation_id=correlation,
        )
        return jsonable_encoder(
            {"specification": asdict(specification), "version": asdict(version)}
        )

    @app.post("/api/v1/organizations/{organization_id}/specifications/{specification_id}/submit")
    async def submit_specification(
        organization_id: UUID,
        specification_id: UUID,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        return jsonable_encoder(
            asdict(
                await use_case.submit_specification(
                    actor_subject=principal.subject,
                    organization_id=organization_id,
                    specification_id=specification_id,
                    correlation_id=correlation,
                )
            )
        )

    @app.post("/api/v1/organizations/{organization_id}/specifications/{specification_id}/approve")
    async def approve_specification(
        organization_id: UUID,
        specification_id: UUID,
        payload: ApprovalDecision,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        specification, work_item = await use_case.approve_specification(
            actor_subject=principal.subject,
            organization_id=organization_id,
            specification_id=specification_id,
            reason=payload.reason,
            correlation_id=correlation,
        )
        return jsonable_encoder(
            {"specification": asdict(specification), "work_item": asdict(work_item)}
        )

    @app.post("/api/v1/organizations/{organization_id}/work-items/{work_item_id}/review")
    async def review_work_item(
        organization_id: UUID,
        work_item_id: UUID,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        return jsonable_encoder(
            asdict(
                await use_case.review_work_item(
                    actor_subject=principal.subject,
                    organization_id=organization_id,
                    work_item_id=work_item_id,
                    correlation_id=correlation,
                )
            )
        )

    @app.post("/api/v1/organizations/{organization_id}/work-items/{work_item_id}/ready")
    async def ready_work_item(
        organization_id: UUID,
        work_item_id: UUID,
        payload: WorkItemReady,
        principal: PrincipalDependency,
        use_case: ServiceDependency,
        correlation: CorrelationDependency,
    ) -> Any:
        return jsonable_encoder(
            asdict(
                await use_case.ready_work_item(
                    actor_subject=principal.subject,
                    organization_id=organization_id,
                    work_item_id=work_item_id,
                    repository_connection_id=payload.repository_connection_id,
                    provider_configuration_id=payload.provider_configuration_id,
                    runner_pool_id=payload.runner_pool_id,
                    budget=Budget(**payload.budget.model_dump()),
                    correlation_id=correlation,
                )
            )
        )

    return app


app = create_app()
