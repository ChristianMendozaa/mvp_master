from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import select, text

from mvp_integrations.application.ports import IntegrationRepository
from mvp_integrations.domain.models import (
    ConnectorInstallation,
    InstallationStatus,
    RepositoryConnection,
)


class Base(DeclarativeBase):
    pass


class InstallationRow(Base):
    __tablename__ = "connector_installations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    external_account_id: Mapped[str] = mapped_column(String(256))
    account_login: Mapped[str] = mapped_column(String(256))
    requested_permissions: Mapped[list[str]] = mapped_column(JSON)
    is_development_substitute: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MembershipProjectionRow(Base):
    __tablename__ = "membership_projection"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(String(300), primary_key=True)
    role: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean)


class InstallationRoutingRow(Base):
    __tablename__ = "installation_routing"
    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_account_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class RepositoryRow(Base):
    __tablename__ = "repository_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "installation_id", "external_repository_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    installation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    external_repository_id: Mapped[str] = mapped_column(String(256))
    owner: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(256))
    default_branch: Mapped[str] = mapped_column(String(256))
    clone_locator: Mapped[str] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean)
    is_development_substitute: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebhookDeliveryRow(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("provider", "delivery_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    delivery_id: Mapped[str] = mapped_column(String(256))
    event_name: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InboxRow(Base):
    __tablename__ = "event_inbox"
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(200))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PostgresIntegrationRepository(IntegrationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_organization(self, organization_id: UUID) -> None:
        await self._session.execute(
            text("select set_config('app.current_organization_id', :value, true)"),
            {"value": str(organization_id)},
        )

    async def role_for(self, organization_id: UUID, subject: str) -> str | None:
        await self.set_organization(organization_id)
        value: str | None = await self._session.scalar(
            select(MembershipProjectionRow.role).where(
                MembershipProjectionRow.organization_id == organization_id,
                MembershipProjectionRow.subject == subject,
                MembershipProjectionRow.active.is_(True),
            )
        )
        return value

    async def upsert_membership(
        self, organization_id: UUID, subject: str, role: str, active: bool
    ) -> None:
        await self.set_organization(organization_id)
        row = await self._session.get(MembershipProjectionRow, (organization_id, subject))
        if row:
            row.role = role
            row.active = active
        else:
            self._session.add(
                MembershipProjectionRow(
                    organization_id=organization_id,
                    subject=subject,
                    role=role,
                    active=active,
                )
            )

    async def record_inbox(self, event_id: UUID, organization_id: UUID, event_type: str) -> bool:
        await self.set_organization(organization_id)
        if await self._session.get(InboxRow, event_id):
            return False
        self._session.add(
            InboxRow(
                event_id=event_id,
                organization_id=organization_id,
                event_type=event_type,
            )
        )
        return True

    async def add_installation(self, installation: ConnectorInstallation) -> None:
        await self.set_organization(installation.organization_id)
        self._session.add(
            InstallationRow(
                id=installation.id,
                organization_id=installation.organization_id,
                provider=installation.provider,
                external_account_id=installation.external_account_id,
                account_login=installation.account_login,
                requested_permissions=list(installation.requested_permissions),
                is_development_substitute=installation.is_development_substitute,
                status=installation.status.value,
                created_at=installation.created_at,
            )
        )
        self._session.add(
            InstallationRoutingRow(
                provider=installation.provider,
                external_account_id=installation.external_account_id,
                organization_id=installation.organization_id,
                installation_id=installation.id,
            )
        )

    async def get_installation(
        self, organization_id: UUID, installation_id: UUID
    ) -> ConnectorInstallation | None:
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(InstallationRow).where(InstallationRow.id == installation_id)
        )
        return self._installation(row) if row else None

    async def organization_for_external_installation(
        self, provider: str, external_account_id: str
    ) -> UUID | None:
        value: UUID | None = await self._session.scalar(
            select(InstallationRoutingRow.organization_id).where(
                InstallationRoutingRow.provider == provider,
                InstallationRoutingRow.external_account_id == external_account_id,
            )
        )
        return value

    async def update_installation(self, installation: ConnectorInstallation) -> None:
        await self.set_organization(installation.organization_id)
        row = await self._session.get(InstallationRow, installation.id)
        if row:
            row.status = installation.status.value

    async def add_repository(self, repository: RepositoryConnection) -> None:
        await self.set_organization(repository.organization_id)
        self._session.add(
            RepositoryRow(
                id=repository.id,
                organization_id=repository.organization_id,
                installation_id=repository.installation_id,
                external_repository_id=repository.external_repository_id,
                owner=repository.owner,
                name=repository.name,
                default_branch=repository.default_branch,
                clone_locator=repository.clone_locator,
                is_private=repository.is_private,
                is_development_substitute=repository.is_development_substitute,
                created_at=repository.created_at,
            )
        )

    async def get_repository(
        self, organization_id: UUID, repository_id: UUID
    ) -> RepositoryConnection | None:
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(RepositoryRow).where(RepositoryRow.id == repository_id)
        )
        return self._repository(row) if row else None

    async def list_repositories(self, organization_id: UUID) -> tuple[RepositoryConnection, ...]:
        await self.set_organization(organization_id)
        rows = (await self._session.scalars(select(RepositoryRow))).all()
        return tuple(self._repository(row) for row in rows)

    async def record_webhook_delivery(
        self,
        *,
        provider: str,
        delivery_id: str,
        organization_id: UUID | None,
        event_name: str,
        payload_hash: str,
    ) -> bool:
        if organization_id is None:
            return False
        await self.set_organization(organization_id)
        exists = await self._session.scalar(
            select(WebhookDeliveryRow.id).where(
                WebhookDeliveryRow.provider == provider,
                WebhookDeliveryRow.delivery_id == delivery_id,
            )
        )
        if exists is not None:
            return False
        self._session.add(
            WebhookDeliveryRow(
                organization_id=organization_id,
                provider=provider,
                delivery_id=delivery_id,
                event_name=event_name,
                payload_hash=payload_hash,
            )
        )
        return True

    async def record_audit(
        self,
        *,
        organization_id: UUID,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        await self.set_organization(organization_id)
        self._session.add(
            AuditRow(
                organization_id=organization_id,
                actor_subject=actor_subject,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
            )
        )

    @staticmethod
    def _installation(row: InstallationRow) -> ConnectorInstallation:
        return ConnectorInstallation(
            id=row.id,
            organization_id=row.organization_id,
            provider=row.provider,
            external_account_id=row.external_account_id,
            account_login=row.account_login,
            requested_permissions=tuple(row.requested_permissions),
            is_development_substitute=row.is_development_substitute,
            status=InstallationStatus(row.status),
            created_at=row.created_at,
        )

    @staticmethod
    def _repository(row: RepositoryRow) -> RepositoryConnection:
        return RepositoryConnection(
            id=row.id,
            organization_id=row.organization_id,
            installation_id=row.installation_id,
            external_repository_id=row.external_repository_id,
            owner=row.owner,
            name=row.name,
            default_branch=row.default_branch,
            clone_locator=row.clone_locator,
            is_private=row.is_private,
            is_development_substitute=row.is_development_substitute,
            created_at=row.created_at,
        )
