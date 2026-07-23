from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    service_name: str = "integrations"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://integrations:local-integrations-only@localhost:5432/integrations",
        alias="INTEGRATIONS_DATABASE_URL",
    )
    oidc_issuer: str = Field(
        default="http://localhost:8081/realms/mvp-master", alias="KEYCLOAK_BROWSER_ISSUER"
    )
    oidc_jwks_url: str = "http://keycloak:8080/realms/mvp-master/protocol/openid-connect/certs"
    oidc_audience: str = Field(default="mvp-api", alias="KEYCLOAK_AUDIENCE")
    allow_development_identity: bool = False
    github_adapter: str = "local"
    github_api_url: str = "https://api.github.com"
    github_webhook_secret_file: str | None = None
    nats_url: str = "nats://localhost:4222"
    internal_service_token: str = ""
