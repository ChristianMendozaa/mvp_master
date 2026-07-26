"""Explicit, reviewed composition of every `AgentRuntime` this runner supports.

No dynamic plugin discovery — matches the rest of this codebase's style of explicit
composition roots. Adding a new runtime means: write one adapter class, add one entry
to `build_agents`, add one entry to `SUPPORTED_RUNTIMES`, and register the runtime's
allowed (provider, authentication_mode) combinations in delivery's
`domain/agent_runtimes.py`.

This registry takes an already-resolved secret value (or `None`), never a
`SecretReference` and never a `SecretResolver` — resolution happens once, on the
host-side daemon, before the job container is launched (see
`entrypoints/daemon.py::run_job` and `adapters/leased_secret_resolver.py`). Nothing
inside the isolated job container calls out to resolve a credential.
"""

from typing import cast

from mvp_runner.adapters.claude_agent_sdk import ClaudeAgentSdkAgent
from mvp_runner.adapters.claude_code_cli import ClaudeCodeCliAgent
from mvp_runner.adapters.codex_cli import CodexCliAgent
from mvp_runner.adapters.deterministic_agent import DeterministicAgent
from mvp_runner.adapters.provider_catalog import ProviderEndpoint
from mvp_runner.application.ports import AgentRuntime

SUPPORTED_RUNTIMES: frozenset[str] = frozenset(
    {"deterministic", "codex-cli", "claude-code-cli", "claude-agent-sdk"}
)

# Every runtime except `deterministic` calls a real model API and therefore needs
# the controlled egress network (see `adapters/egress_network.py` and
# `entrypoints/daemon.py::run_job`). `deterministic` never appears here — it stays
# unconditionally `network_disabled=True`, with no code path that can change that.
EGRESS_REQUIRED_RUNTIMES: frozenset[str] = SUPPORTED_RUNTIMES - {"deterministic"}


def build_agents(*, secret: str | None, endpoint: ProviderEndpoint) -> dict[str, AgentRuntime]:
    """Construct a fresh registry of every runtime for one job.

    `secret` and `endpoint` are shared across every adapter because a single job
    payload names exactly one (runtime, provider, authentication_mode) triple — only
    the adapter selected by `runtime` will ever actually read them.

    Each concrete adapter is `cast` to `AgentRuntime` because the `name` /
    `is_development_substitute` class attributes on a non-`@runtime_checkable`
    structural Protocol don't satisfy mypy's dict-value variance check on their
    own — the same cast the previous inline registry in `entrypoints/job.py` used.
    """
    return {
        "deterministic": cast(AgentRuntime, DeterministicAgent()),
        "codex-cli": cast(AgentRuntime, CodexCliAgent(secret=secret, endpoint=endpoint)),
        "claude-code-cli": cast(AgentRuntime, ClaudeCodeCliAgent(secret=secret, endpoint=endpoint)),
        "claude-agent-sdk": cast(
            AgentRuntime, ClaudeAgentSdkAgent(secret=secret, endpoint=endpoint)
        ),
    }
