from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    delivery_url: str = "http://delivery:8000"
    integrations_url: str = "http://integrations:8000"
    runner_id: str = "00000000-0000-0000-0000-000000000006"
    runner_credential: str = "local-runner-credential-only"
    workspace_root: Path = Path("/workspaces")
    fixture_path: Path = Path("/fixtures/sample-webapp")
    job_image: str = "mvp-runner-job:local"
    poll_seconds: float = 1.0
