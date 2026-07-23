from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    service_name: str = "control-plane"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://control_plane:local-control-plane-only@localhost:5432/control_plane",
        alias="CONTROL_PLANE_DATABASE_URL",
    )
    oidc_issuer: str = Field(
        default="http://localhost:8081/realms/mvp-master", alias="KEYCLOAK_BROWSER_ISSUER"
    )
    oidc_jwks_url: str = "http://keycloak:8080/realms/mvp-master/protocol/openid-connect/certs"
    oidc_audience: str = Field(default="mvp-api", alias="KEYCLOAK_AUDIENCE")
    allow_development_identity: bool = False
    nats_url: str = "nats://localhost:4222"
