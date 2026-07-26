"""Static, reviewed catalog mapping a `provider` value to its API endpoint.

This is deliberately NOT a user- or tenant-configurable mapping: a tenant never
supplies an arbitrary base URL (that would be an SSRF / secret-exfiltration risk,
since the resolved auth token is sent to whatever host is configured). Adding a new
provider means adding one reviewed entry here — that is the whole extensibility
story for this module.

This module has no third-party dependencies so it can be imported both by the
host-side daemon (to compute the egress allowlist before the job container starts)
and by the in-container CLI adapters (to know which environment variables the daemon
has already populated). Neither side performs network I/O from here, and this module
never sees a resolved secret value — only identifiers.
"""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from mvp_runner.domain.errors import UnknownProvider


class ProviderAuthStyle(StrEnum):
    """Which environment variable a resolved secret is written to.

    This is the discriminator, not the provider identity, because it is the only
    thing an `AgentRuntime` adapter actually branches on. `zhipu-glm` and
    `moonshot-kimi` share `ANTHROPIC_AUTH_TOKEN` + a base URL override; first-party
    `anthropic` uses `ANTHROPIC_API_KEY` with no override.
    """

    NONE = "NONE"
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    ANTHROPIC_AUTH_TOKEN = "ANTHROPIC_AUTH_TOKEN"  # noqa: S105 -- env var name, not a secret value
    OPENAI_API_KEY = "OPENAI_API_KEY"


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    """Describes how to reach a provider's API and how the agent process authenticates.

    `base_url` is `None` for a provider's own first-party API (nothing to override).
    It is set for a provider reached *through* another vendor's CLI/SDK pointed at an
    Anthropic- or OpenAI-compatible endpoint (e.g. a Chinese model vendor served
    through the Claude Code CLI).
    """

    provider: str
    display_name: str
    auth_style: ProviderAuthStyle
    base_url: str | None
    egress_hosts: tuple[str, ...]
    compatible_runtimes: tuple[str, ...]


_ENTRIES: tuple[ProviderEndpoint, ...] = (
    ProviderEndpoint(
        provider="local",
        display_name="Local development substitute",
        auth_style=ProviderAuthStyle.NONE,
        base_url=None,
        egress_hosts=(),
        compatible_runtimes=("deterministic",),
    ),
    ProviderEndpoint(
        provider="anthropic",
        display_name="Anthropic",
        auth_style=ProviderAuthStyle.ANTHROPIC_API_KEY,
        base_url=None,
        egress_hosts=("api.anthropic.com",),
        compatible_runtimes=("claude-agent-sdk", "claude-code-cli"),
    ),
    ProviderEndpoint(
        provider="openai",
        display_name="OpenAI",
        auth_style=ProviderAuthStyle.OPENAI_API_KEY,
        base_url=None,
        egress_hosts=("api.openai.com", "chatgpt.com"),
        compatible_runtimes=("codex-cli",),
    ),
    ProviderEndpoint(
        provider="zhipu-glm",
        display_name="Zhipu GLM",
        auth_style=ProviderAuthStyle.ANTHROPIC_AUTH_TOKEN,
        base_url="https://open.bigmodel.cn/api/anthropic",
        egress_hosts=("open.bigmodel.cn",),
        compatible_runtimes=("claude-code-cli",),
    ),
    ProviderEndpoint(
        provider="moonshot-kimi",
        display_name="Moonshot Kimi",
        auth_style=ProviderAuthStyle.ANTHROPIC_AUTH_TOKEN,
        base_url="https://api.moonshot.ai/anthropic",
        egress_hosts=("api.moonshot.ai",),
        compatible_runtimes=("claude-code-cli",),
    ),
)

# Adding a new provider = adding one entry above. Nothing else in this module changes.
PROVIDER_CATALOG: MappingProxyType[str, ProviderEndpoint] = MappingProxyType(
    {entry.provider: entry for entry in _ENTRIES}
)


def endpoint_for(provider: str) -> ProviderEndpoint:
    """Look up a provider's endpoint configuration.

    Raises `UnknownProvider` rather than falling back to any default — an
    unrecognized provider must fail loudly, never silently substitute another
    provider or auth style (see AGENTS.md: "Never silently switch provider, model,
    authentication, or billing mode").
    """
    try:
        return PROVIDER_CATALOG[provider]
    except KeyError as error:
        raise UnknownProvider(f"unknown model provider: {provider!r}") from error


def environment_for(endpoint: ProviderEndpoint, secret: str | None) -> dict[str, str]:
    """Build the environment variables an agent process needs for this endpoint.

    Returns `{}` for `ProviderAuthStyle.NONE`. Never logs or otherwise surfaces
    `secret` — callers must treat the returned mapping with the same care as the
    secret itself.
    """
    if endpoint.auth_style is ProviderAuthStyle.NONE:
        return {}
    if secret is None:
        raise ValueError(
            f"provider {endpoint.provider!r} requires a resolved secret but none was given"
        )
    environment = {endpoint.auth_style.value: secret}
    if endpoint.base_url is not None:
        environment["ANTHROPIC_BASE_URL"] = endpoint.base_url
    return environment


def allowlisted_hosts() -> tuple[str, ...]:
    """Union of every provider's egress hosts, for the egress-proxy allowlist."""
    hosts: list[str] = []
    for entry in PROVIDER_CATALOG.values():
        for host in entry.egress_hosts:
            if host not in hosts:
                hosts.append(host)
    return tuple(hosts)
