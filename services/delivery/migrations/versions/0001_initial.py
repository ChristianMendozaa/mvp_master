"""Initial delivery schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "delivery_0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "membership_projection",
    "provider_configurations",
    "runner_pools",
    "runner_enrollment_tokens",
    "runners",
    "runner_jobs",
    "executions",
    "execution_events",
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
        "provider_configurations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("runtime", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("authentication_mode", sa.String(64), nullable=False),
        sa.Column("secret_reference", postgresql.JSONB()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_development_substitute", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "runner_pools",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("runner_type", sa.String(64), nullable=False),
    )
    op.create_table(
        "runner_enrollment_tokens",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("pool_id", uuid, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "runner_enrollment_routing",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("organization_id", uuid, nullable=False),
    )
    op.create_table(
        "runners",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("pool_id", uuid, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runner_credential_routing",
        sa.Column("credential_hash", sa.String(64), primary_key=True),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("runner_id", uuid, nullable=False),
    )
    op.create_table(
        "executions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("project_id", uuid, nullable=False, index=True),
        sa.Column("work_item_id", uuid, nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("repository_connection_id", uuid, nullable=False),
        sa.Column("provider_configuration_id", uuid, nullable=False),
        sa.Column("runner_pool_id", uuid, nullable=False),
        sa.Column("budget", postgresql.JSONB(), nullable=False),
        sa.Column("approval_status", sa.String(32), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("cost_minor", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("result_reference", postgresql.JSONB()),
        sa.UniqueConstraint("organization_id", "work_item_id"),
    )
    op.create_table(
        "execution_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("execution_id", uuid, nullable=False, index=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("execution_id", "sequence"),
    )
    op.create_table(
        "runner_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("execution_id", uuid, nullable=False, index=True),
        sa.Column("pool_id", uuid, nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("leased_by_runner_id", uuid),
        sa.Column("leased_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "execution_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("actor_subject", sa.String(300), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
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
    op.create_table(
        "workflow_commands",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("execution_id", uuid, nullable=False, index=True),
        sa.Column("command", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(300)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
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
        CREATE FUNCTION prevent_delivery_audit_mutation() RETURNS trigger AS $$
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
        FOR EACH ROW EXECUTE FUNCTION prevent_delivery_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS prevent_delivery_audit_mutation() CASCADE")
    for table in (
        "workflow_commands",
        "audit_events",
        "event_inbox",
        "execution_events",
        "executions",
        "runners",
        "runner_credential_routing",
        "runner_jobs",
        "runner_enrollment_routing",
        "runner_enrollment_tokens",
        "runner_pools",
        "provider_configurations",
        "membership_projection",
    ):
        op.drop_table(table)
