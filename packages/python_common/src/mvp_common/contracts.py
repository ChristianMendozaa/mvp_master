from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SecretReference(ContractModel):
    store: str = Field(min_length=1, max_length=64)
    namespace: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=256)
    version: str | None = Field(default=None, max_length=128)

    @field_validator("store", "namespace", "key")
    @classmethod
    def reject_secret_values(cls, value: str) -> str:
        if "=" in value or "\n" in value:
            raise ValueError("secret references must contain identifiers, not values")
        return value


class ExternalReference(ContractModel):
    provider: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=256)
    repository: str | None = Field(default=None, max_length=512)
    resource_type: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=512)


class EventEnvelope(ContractModel):
    specversion: str = "1.0"
    id: UUID
    source: str
    type: str
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    subject: str
    organization_id: UUID
    aggregate_version: int = Field(ge=1)
    correlation_id: UUID
    causation_id: UUID | None = None
    traceparent: str | None = None
    data: dict[str, Any]
