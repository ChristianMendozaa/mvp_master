from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    service_name: str = "delivery"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://delivery:local-delivery-only@localhost:5432/delivery",
        alias="DELIVERY_DATABASE_URL",
    )
    oidc_issuer: str = Field(
        default="http://localhost:8081/realms/mvp-master", alias="KEYCLOAK_BROWSER_ISSUER"
    )
    oidc_jwks_url: str = "http://keycloak:8080/realms/mvp-master/protocol/openid-connect/certs"
    oidc_audience: str = Field(default="mvp-api", alias="KEYCLOAK_AUDIENCE")
    allow_development_identity: bool = False
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    nats_url: str = "nats://localhost:4222"
    integrations_url: str = "http://localhost:8001"
    internal_service_token: str = ""
