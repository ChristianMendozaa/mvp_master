"""Initial control-plane schema.

Revision ID: control_0001
Revises:
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "control_0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "memberships",
    "projects",
    "intake_requests",
    "specifications",
    "specification_versions",
    "approvals",
    "work_items",
    "audit_events",
    "event_outbox",
)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "organizations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("subject", sa.String(300), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
    )
    op.create_table(
        "membership_routing",
        sa.Column("subject", sa.String(300), primary_key=True),
        sa.Column("organization_id", uuid, primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("execution_approval_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "intake_requests",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("project_id", uuid, nullable=False, index=True),
        sa.Column("client_id", uuid),
        sa.Column("submitted_by", sa.String(300), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("intended_users", sa.Text(), nullable=False),
        sa.Column("required_functionality", postgresql.JSONB(), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "specifications",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("project_id", uuid, nullable=False, index=True),
        sa.Column("intake_id", uuid, nullable=False, unique=True),
        sa.Column("current_version_id", uuid, nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
    )
    op.create_table(
        "specification_versions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("specification_id", uuid, nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("intended_users", sa.Text(), nullable=False),
        sa.Column("requirements", postgresql.JSONB(), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("specification_id", "version"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", uuid, nullable=False),
        sa.Column("subject_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "work_items",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("project_id", uuid, nullable=False, index=True),
        sa.Column("specification_version_id", uuid, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("repository_connection_id", uuid),
        sa.Column("provider_configuration_id", uuid),
        sa.Column("runner_pool_id", uuid),
        sa.Column("budget", postgresql.JSONB()),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", uuid, nullable=False),
        sa.Column("correlation_id", uuid, nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "event_outbox",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "event_outbox_routing",
        sa.Column("event_id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False),
    )

    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organizations_tenant_isolation ON organizations
        USING (id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        WITH CHECK (id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        """
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

    op.execute(
        """
        CREATE FUNCTION prevent_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation() CASCADE")
    for table in (
        "event_outbox",
        "event_outbox_routing",
        "audit_events",
        "work_items",
        "approvals",
        "specification_versions",
        "specifications",
        "intake_requests",
        "projects",
        "memberships",
        "membership_routing",
        "organizations",
    ):
        op.drop_table(table)
