from mvp_runner.adapters.agent_registry import (
    EGRESS_REQUIRED_RUNTIMES,
    SUPPORTED_RUNTIMES,
    build_agents,
)
from mvp_runner.adapters.provider_catalog import endpoint_for


def test_build_agents_contains_every_supported_runtime() -> None:
    agents = build_agents(secret=None, endpoint=endpoint_for("local"))
    assert set(agents) == SUPPORTED_RUNTIMES
    assert {
        "deterministic",
        "codex-cli",
        "claude-code-cli",
        "claude-agent-sdk",
    } == SUPPORTED_RUNTIMES


def test_only_deterministic_is_a_development_substitute() -> None:
    agents = build_agents(secret=None, endpoint=endpoint_for("local"))
    for name, agent in agents.items():
        if name == "deterministic":
            assert agent.is_development_substitute is True
        else:
            assert agent.is_development_substitute is False


def test_egress_required_runtimes_excludes_only_deterministic() -> None:
    assert "deterministic" not in EGRESS_REQUIRED_RUNTIMES
    assert SUPPORTED_RUNTIMES - {"deterministic"} == EGRESS_REQUIRED_RUNTIMES


async def test_every_agent_reports_capabilities() -> None:
    agents = build_agents(secret="secret", endpoint=endpoint_for("anthropic"))
    for agent in agents.values():
        capabilities = await agent.capabilities()
        assert capabilities.supported_authentication_modes
