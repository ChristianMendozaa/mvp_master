import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.integration
async def test_connector_setup_attempts_are_hidden_across_tenants() -> None:
    database_url = os.environ.get("INTEGRATIONS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("INTEGRATIONS_TEST_DATABASE_URL is not configured")
    engine = create_async_engine(database_url)
    organization_one = uuid4()
    organization_two = uuid4()
    state_hash = "a" * 64
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text("select set_config('app.current_organization_id', :value, true)"),
                    {"value": str(organization_one)},
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO connector_setup_attempts (
                            state_hash, organization_id, actor_subject,
                            configuration_id, expires_at, used_at
                        )
                        VALUES (
                            :state_hash, :organization_id, 'integration-test',
                            :configuration_id, :expires_at, NULL
                        )
                        """
                    ),
                    {
                        "state_hash": state_hash,
                        "organization_id": organization_one,
                        "configuration_id": uuid4(),
                        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
                    },
                )
                own_count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM connector_setup_attempts "
                        "WHERE state_hash = :state_hash"
                    ),
                    {"state_hash": state_hash},
                )
                await connection.execute(
                    text("select set_config('app.current_organization_id', :value, true)"),
                    {"value": str(organization_two)},
                )
                other_count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM connector_setup_attempts "
                        "WHERE state_hash = :state_hash"
                    ),
                    {"state_hash": state_hash},
                )
                assert own_count == 1
                assert other_count == 0
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
