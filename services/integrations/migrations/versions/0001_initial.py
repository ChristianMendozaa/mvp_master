"""Initial integrations schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "integrations_0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "membership_projection",
    "connector_installations",
    "repository_connections",
    "audit_events",
    "event_inbox",
)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "membership_projection",
        sa.Column("organization_id", uuid, primary_key=True),
        sa.Column("subject", sa.String(300), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "connector_installations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_account_id", sa.String(256), nullable=False),
        sa.Column("account_login", sa.String(256), nullable=False),
        sa.Column("requested_permissions", postgresql.JSONB(), nullable=False),
        sa.Column("is_development_substitute", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repository_connections",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("installation_id", uuid, nullable=False, index=True),
        sa.Column("external_repository_id", sa.String(256), nullable=False),
        sa.Column("owner", sa.String(256), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("default_branch", sa.String(256), nullable=False),
        sa.Column("clone_locator", sa.Text(), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("is_development_substitute", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "installation_id", "external_repository_id"
        ),
    )
    op.create_table(
        "installation_routing",
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("external_account_id", sa.String(256), primary_key=True),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("installation_id", uuid, nullable=False),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", uuid),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("delivery_id", sa.String(256), nullable=False),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("provider", "delivery_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
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
        "event_inbox",
        sa.Column("event_id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
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
    op.execute("ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY webhook_deliveries_tenant_isolation ON webhook_deliveries
        USING (
            organization_id IS NOT NULL AND organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        WITH CHECK (
            organization_id IS NOT NULL AND organization_id =
            nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    for table in (
        "audit_events",
        "event_inbox",
        "webhook_deliveries",
        "installation_routing",
        "repository_connections",
        "connector_installations",
        "membership_projection",
    ):
        op.drop_table(table)
