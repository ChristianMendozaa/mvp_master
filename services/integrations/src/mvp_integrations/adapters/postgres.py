from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import select, text

from mvp_integrations.application.ports import IntegrationRepository
from mvp_integrations.domain.models import (
    ConfigurationHealth,
    ConnectorInstallation,
    InstallationStatus,
    RepositoryAccessStatus,
    RepositoryConnection,
    SourceControlConfiguration,
    WebhookMode,
)


class Base(DeclarativeBase):
    pass


class SourceControlConfigurationRow(Base):
    __tablename__ = "source_control_configurations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(64))
    web_base_url: Mapped[str] = mapped_column(String(512))
    api_base_url: Mapped[str] = mapped_column(String(512))
    api_version: Mapped[str] = mapped_column(String(32))
    app_id: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[str] = mapped_column(String(256))
    app_slug: Mapped[str] = mapped_column(String(256))
    private_key_reference: Mapped[dict[str, str | None]] = mapped_column(JSON)
    client_secret_reference: Mapped[dict[str, str | None]] = mapped_column(JSON)
    webhook_secret_reference: Mapped[dict[str, str | None]] = mapped_column(JSON)
    webhook_mode: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean)
    health: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlatformAuditRow(Base):
    __tablename__ = "platform_audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PlatformSetupAttemptRow(Base):
    __tablename__ = "platform_setup_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConnectorSetupAttemptRow(Base):
    __tablename__ = "connector_setup_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    actor_subject: Mapped[str] = mapped_column(String(300))
    configuration_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCapabilityRedemptionRow(Base):
    __tablename__ = "source_capability_redemptions"
    capability_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InstallationRow(Base):
    __tablename__ = "connector_installations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    external_account_id: Mapped[str] = mapped_column(String(256))
    account_login: Mapped[str] = mapped_column(String(256))
    requested_permissions: Mapped[list[str]] = mapped_column(JSON)
    is_development_substitute: Mapped[bool] = mapped_column(Boolean)
    provider_configuration_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    granted_permissions: Mapped[list[str]] = mapped_column(JSON)
    repository_selection: Mapped[str] = mapped_column(String(32))
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    access_status: Mapped[str] = mapped_column(String(32))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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

    async def create_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, expires_at: datetime
    ) -> None:
        self._session.add(
            PlatformSetupAttemptRow(
                state_hash=state_hash,
                actor_subject=actor_subject,
                expires_at=expires_at,
                used_at=None,
            )
        )

    async def consume_platform_setup_attempt(
        self, state_hash: str, actor_subject: str, now: datetime
    ) -> bool:
        row = await self._session.scalar(
            select(PlatformSetupAttemptRow)
            .where(PlatformSetupAttemptRow.state_hash == state_hash)
            .with_for_update()
        )
        if (
            row is None
            or row.actor_subject != actor_subject
            or row.used_at is not None
            or row.expires_at <= now
        ):
            return False
        row.used_at = datetime.now(UTC)
        return True

    async def create_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        configuration_id: UUID,
        expires_at: datetime,
    ) -> None:
        await self.set_organization(organization_id)
        self._session.add(
            ConnectorSetupAttemptRow(
                state_hash=state_hash,
                organization_id=organization_id,
                actor_subject=actor_subject,
                configuration_id=configuration_id,
                expires_at=expires_at,
                used_at=None,
            )
        )

    async def consume_connector_setup_attempt(
        self,
        organization_id: UUID,
        state_hash: str,
        actor_subject: str,
        now: datetime,
    ) -> UUID | None:
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(ConnectorSetupAttemptRow)
            .where(ConnectorSetupAttemptRow.state_hash == state_hash)
            .with_for_update()
        )
        if (
            row is None
            or row.organization_id != organization_id
            or row.actor_subject != actor_subject
            or row.used_at is not None
            or row.expires_at <= now
        ):
            return None
        row.used_at = datetime.now(UTC)
        return row.configuration_id

    async def redeem_source_capability(
        self,
        organization_id: UUID,
        capability_id: str,
        expires_at: datetime,
    ) -> bool:
        await self.set_organization(organization_id)
        existing = await self._session.get(SourceCapabilityRedemptionRow, capability_id)
        if existing:
            return False
        self._session.add(
            SourceCapabilityRedemptionRow(
                capability_id=capability_id,
                organization_id=organization_id,
                expires_at=expires_at,
                redeemed_at=datetime.now(UTC),
            )
        )
        return True

    async def add_source_control_configuration(
        self, configuration: SourceControlConfiguration
    ) -> None:
        self._session.add(
            SourceControlConfigurationRow(
                id=configuration.id,
                display_name=configuration.display_name,
                provider=configuration.provider,
                web_base_url=configuration.web_base_url,
                api_base_url=configuration.api_base_url,
                api_version=configuration.api_version,
                app_id=configuration.app_id,
                client_id=configuration.client_id,
                app_slug=configuration.app_slug,
                private_key_reference=configuration.private_key_reference,
                client_secret_reference=configuration.client_secret_reference,
                webhook_secret_reference=configuration.webhook_secret_reference,
                webhook_mode=configuration.webhook_mode.value,
                enabled=configuration.enabled,
                health=configuration.health.value,
                created_at=configuration.created_at,
            )
        )

    async def get_source_control_configuration(
        self, configuration_id: UUID
    ) -> SourceControlConfiguration | None:
        row = await self._session.get(SourceControlConfigurationRow, configuration_id)
        return self._configuration(row) if row else None

    async def source_control_configuration_for_app_id(
        self, provider: str, app_id: str
    ) -> SourceControlConfiguration | None:
        row = await self._session.scalar(
            select(SourceControlConfigurationRow).where(
                SourceControlConfigurationRow.provider == provider,
                SourceControlConfigurationRow.app_id == app_id,
            )
        )
        return self._configuration(row) if row else None

    async def list_source_control_configurations(
        self,
    ) -> tuple[SourceControlConfiguration, ...]:
        rows = (await self._session.scalars(select(SourceControlConfigurationRow))).all()
        return tuple(self._configuration(row) for row in rows)

    async def update_source_control_configuration_health(
        self, configuration_id: UUID, health: str, enabled: bool
    ) -> None:
        row = await self._session.get(SourceControlConfigurationRow, configuration_id)
        if row:
            row.health = health
            row.enabled = enabled

    async def record_platform_audit(
        self,
        *,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: UUID,
        details: dict[str, object],
    ) -> None:
        self._session.add(
            PlatformAuditRow(
                actor_subject=actor_subject,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
            )
        )

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
                provider_configuration_id=installation.provider_configuration_id,
                granted_permissions=list(installation.granted_permissions),
                repository_selection=installation.repository_selection,
                last_reconciled_at=installation.last_reconciled_at,
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

    async def installation_for_external(
        self, organization_id: UUID, provider: str, external_account_id: str
    ) -> ConnectorInstallation | None:
        await self.set_organization(organization_id)
        row = await self._session.scalar(
            select(InstallationRow).where(
                InstallationRow.organization_id == organization_id,
                InstallationRow.provider == provider,
                InstallationRow.external_account_id == external_account_id,
            )
        )
        return self._installation(row) if row else None

    async def list_installation_routes(self) -> tuple[tuple[UUID, UUID], ...]:
        rows = (
            await self._session.execute(
                select(
                    InstallationRoutingRow.organization_id,
                    InstallationRoutingRow.installation_id,
                )
            )
        ).all()
        return tuple((row.organization_id, row.installation_id) for row in rows)

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
                access_status=repository.access_status.value,
                last_seen_at=repository.last_seen_at,
                revoked_at=repository.revoked_at,
                created_at=repository.created_at,
            )
        )

    async def upsert_repository(self, repository: RepositoryConnection) -> None:
        await self.set_organization(repository.organization_id)
        row = await self._session.scalar(
            select(RepositoryRow).where(
                RepositoryRow.organization_id == repository.organization_id,
                RepositoryRow.installation_id == repository.installation_id,
                RepositoryRow.external_repository_id == repository.external_repository_id,
            )
        )
        if row is None:
            await self.add_repository(repository)
            return
        row.owner = repository.owner
        row.name = repository.name
        row.default_branch = repository.default_branch
        row.clone_locator = repository.clone_locator
        row.is_private = repository.is_private
        row.access_status = repository.access_status.value
        row.last_seen_at = repository.last_seen_at
        row.revoked_at = repository.revoked_at

    async def revoke_repositories_except(
        self,
        organization_id: UUID,
        installation_id: UUID,
        active_external_ids: set[str],
        revoked_at: datetime,
    ) -> None:
        await self.set_organization(organization_id)
        rows = (
            await self._session.scalars(
                select(RepositoryRow).where(RepositoryRow.installation_id == installation_id)
            )
        ).all()
        for row in rows:
            if row.external_repository_id not in active_external_ids:
                row.access_status = RepositoryAccessStatus.REVOKED.value
                row.revoked_at = revoked_at

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
    def _configuration(row: SourceControlConfigurationRow) -> SourceControlConfiguration:
        return SourceControlConfiguration(
            id=row.id,
            display_name=row.display_name,
            provider=row.provider,
            web_base_url=row.web_base_url,
            api_base_url=row.api_base_url,
            api_version=row.api_version,
            app_id=row.app_id,
            client_id=row.client_id,
            app_slug=row.app_slug,
            private_key_reference=row.private_key_reference,
            client_secret_reference=row.client_secret_reference,
            webhook_secret_reference=row.webhook_secret_reference,
            webhook_mode=WebhookMode(row.webhook_mode),
            enabled=row.enabled,
            health=ConfigurationHealth(row.health),
            created_at=row.created_at,
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
            provider_configuration_id=row.provider_configuration_id,
            granted_permissions=tuple(row.granted_permissions),
            repository_selection=row.repository_selection,
            last_reconciled_at=row.last_reconciled_at,
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
            access_status=RepositoryAccessStatus(row.access_status),
            last_seen_at=row.last_seen_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )
