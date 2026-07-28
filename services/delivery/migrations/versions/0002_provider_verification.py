"""Add asynchronous provider verification jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "delivery_0002"
down_revision = "delivery_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "provider_verifications",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("provider_configuration_id", uuid, nullable=False, index=True),
        sa.Column("pool_id", uuid, nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("leased_by_runner_id", uuid),
        sa.Column("leased_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.execute("ALTER TABLE provider_verifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_verifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY provider_verifications_tenant_isolation ON provider_verifications
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


def downgrade() -> None:
    op.drop_table("provider_verifications")
