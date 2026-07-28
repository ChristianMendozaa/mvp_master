"""Add tenant-owned model credential metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "integrations_0003"
down_revision = "integrations_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "model_credentials",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("secret_reference", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.execute("ALTER TABLE model_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE model_credentials FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY model_credentials_tenant_isolation ON model_credentials
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
    op.drop_table("model_credentials")
