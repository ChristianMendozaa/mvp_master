from pathlib import Path

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
    github_web_url: str = "https://github.com"
    github_api_version: str = "2026-03-10"
    github_webhook_secret_file: str | None = None
    public_base_url: str = "http://localhost:3000"
    platform_operator_claim: str = "mvp_master_platform_operator"
    encrypted_secret_root: Path = Path("/var/lib/mvp-master/secrets")
    secret_master_key_file: Path | None = None
    nats_url: str = "nats://localhost:4222"
    internal_service_token: str = ""
