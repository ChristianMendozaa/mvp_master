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

    # Egress is off by default — enabling it for real (non-deterministic) agent
    # runtimes is an explicit, reviewed deployment decision, matching the
    # AGENT_ADAPTER=deterministic default already documented in `.env.example`. See
    # docs/adrs/0009-scoped-model-provider-egress.md. When False, a job requesting a
    # real-agent runtime fails loudly (a normalized ERROR result) rather than
    # silently running without network.
    agent_egress_enabled: bool = False
    agent_egress_network: str = "mvp-agent-egress"
    agent_egress_proxy_image: str = "mvp-agent-egress-proxy:local"
    agent_egress_proxy_port: int = 3128

    # Read-only mounts for LOCAL_SESSION (subscription) authentication. Populated by
    # a CUSTOMER_HOSTED runner operator who has already run `claude /login` /
    # `codex login` once on this host. The adapter copies the mounted contents into
    # the job container's writable HOME at start — see
    # `adapters/claude_code_cli.py::_prepare_local_session` and the analogous
    # handling in `adapters/codex_cli.py`.
    claude_session_path: Path | None = None
    codex_session_path: Path | None = None
