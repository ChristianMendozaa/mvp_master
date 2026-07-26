"""Add real GitHub App configuration and repository lifecycle fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "integrations_0002"
down_revision = "integrations_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "source_control_configurations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("web_base_url", sa.String(512), nullable=False),
        sa.Column("api_base_url", sa.String(512), nullable=False),
        sa.Column("api_version", sa.String(32), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(256), nullable=False),
        sa.Column("app_slug", sa.String(256), nullable=False),
        sa.Column("private_key_reference", postgresql.JSONB(), nullable=False),
        sa.Column("client_secret_reference", postgresql.JSONB(), nullable=False),
        sa.Column("webhook_secret_reference", postgresql.JSONB(), nullable=False),
        sa.Column("webhook_mode", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "app_id"),
    )
    op.create_table(
        "platform_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", uuid, nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "platform_setup_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "connector_setup_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("configuration_id", uuid, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "source_capability_redemptions",
        sa.Column("capability_id", sa.String(64), primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE connector_setup_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connector_setup_attempts FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY connector_setup_attempts_tenant_isolation ON connector_setup_attempts
        USING (
            organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        WITH CHECK (
            organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        """
    )
    op.execute("ALTER TABLE source_capability_redemptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_capability_redemptions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY source_capability_redemptions_tenant_isolation
        ON source_capability_redemptions
        USING (
            organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        WITH CHECK (
            organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        """
    )
    op.add_column(
        "connector_installations",
        sa.Column("provider_configuration_id", uuid, nullable=True),
    )
    op.add_column(
        "connector_installations",
        sa.Column(
            "granted_permissions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "connector_installations",
        sa.Column(
            "repository_selection",
            sa.String(32),
            nullable=False,
            server_default="SELECTED",
        ),
    )
    op.add_column(
        "connector_installations",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "repository_connections",
        sa.Column(
            "access_status",
            sa.String(32),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.add_column(
        "repository_connections",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "repository_connections",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_connections", "revoked_at")
    op.drop_column("repository_connections", "last_seen_at")
    op.drop_column("repository_connections", "access_status")
    op.drop_column("connector_installations", "last_reconciled_at")
    op.drop_column("connector_installations", "repository_selection")
    op.drop_column("connector_installations", "granted_permissions")
    op.drop_column("connector_installations", "provider_configuration_id")
    op.drop_table("source_capability_redemptions")
    op.drop_table("connector_setup_attempts")
    op.drop_table("platform_setup_attempts")
    op.drop_table("platform_audit_events")
    op.drop_table("source_control_configurations")
