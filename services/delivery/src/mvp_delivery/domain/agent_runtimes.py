"""Canonical, reviewed table of which (provider, authentication_mode) combinations
each agent `runtime` supports.

This is domain policy over identifiers only — no base URLs, no provider SDKs, no I/O.
Base URLs and how a runtime actually talks to a provider live in the runner's own
`adapters/provider_catalog.py`; that module is the runner's business, not delivery's.
Keeping both in sync (a runtime named here must exist as a registered runtime in the
runner, and a provider named here must have a catalog entry there) is a repo-review
concern, checked by a cross-service test in each package's test suite.

Adding a new provider or runtime means adding one entry here plus the matching entry
in the runner — nothing else in delivery's domain layer changes.

Operates on plain strings (not the `AuthenticationMode` enum) deliberately: this
module is imported by `domain/models.py`'s `AgentProviderConfiguration.__post_init__`,
and `AuthenticationMode` is defined in that same module — importing it back here
would create a circular import. Callers pass `authentication_mode.value`.
"""

from dataclasses import dataclass
from types import MappingProxyType

from mvp_delivery.domain.errors import UnsupportedProviderConfiguration


@dataclass(frozen=True, slots=True)
class RuntimeCompatibility:
    runtime: str
    providers: frozenset[str]
    authentication_modes: frozenset[str]
    is_development_substitute: bool
    # A subscription session (`LOCAL_SESSION`) authenticates one specific account
    # with one specific first-party provider — it cannot be pointed at a
    # third-party endpoint. `None` when the runtime doesn't support `LOCAL_SESSION`
    # at all (already excluded via `authentication_modes` in that case). Explicit
    # per-runtime rather than a single global constant: `codex-cli`'s subscription
    # provider is `openai`, `claude-code-cli`'s is `anthropic` — there is no one
    # provider that's right for every runtime.
    local_session_provider: str | None


@dataclass(frozen=True, slots=True)
class AgentCatalogEntry:
    """A reviewed user-facing choice.

    Model identifiers are code-owned rather than tenant input. Updating one is a
    reviewed release change, so a provider cannot silently move an organization to
    a different model.
    """

    provider: str
    provider_display_name: str
    runtime: str
    runtime_display_name: str
    models: tuple[str, ...]
    recommended_model: str
    tier: str


RUNTIME_COMPATIBILITY: MappingProxyType[str, RuntimeCompatibility] = MappingProxyType(
    {
        "deterministic": RuntimeCompatibility(
            runtime="deterministic",
            providers=frozenset({"local"}),
            authentication_modes=frozenset({"NONE"}),
            is_development_substitute=True,
            local_session_provider=None,
        ),
        "codex-cli": RuntimeCompatibility(
            runtime="codex-cli",
            providers=frozenset({"openai"}),
            authentication_modes=frozenset({"LOCAL_SESSION", "API_KEY_REFERENCE"}),
            is_development_substitute=False,
            local_session_provider="openai",
        ),
        "claude-code-cli": RuntimeCompatibility(
            runtime="claude-code-cli",
            providers=frozenset({"anthropic", "zhipu-glm", "moonshot-kimi"}),
            authentication_modes=frozenset({"LOCAL_SESSION", "API_KEY_REFERENCE"}),
            is_development_substitute=False,
            local_session_provider="anthropic",
        ),
        "claude-agent-sdk": RuntimeCompatibility(
            runtime="claude-agent-sdk",
            providers=frozenset({"anthropic"}),
            authentication_modes=frozenset({"API_KEY_REFERENCE"}),
            is_development_substitute=False,
            local_session_provider=None,
        ),
    }
)


AGENT_CATALOG: tuple[AgentCatalogEntry, ...] = (
    AgentCatalogEntry(
        provider="openai",
        provider_display_name="OpenAI",
        runtime="codex-cli",
        runtime_display_name="Codex",
        models=("gpt-5.1-codex", "gpt-5.1-codex-max"),
        recommended_model="gpt-5.1-codex",
        tier="PRIMARY",
    ),
    AgentCatalogEntry(
        provider="anthropic",
        provider_display_name="Anthropic",
        runtime="claude-code-cli",
        runtime_display_name="Claude Code",
        models=("claude-opus-5",),
        recommended_model="claude-opus-5",
        tier="PRIMARY",
    ),
    AgentCatalogEntry(
        provider="anthropic",
        provider_display_name="Anthropic",
        runtime="claude-agent-sdk",
        runtime_display_name="Claude Agent SDK",
        models=("claude-opus-5",),
        recommended_model="claude-opus-5",
        tier="ADVANCED",
    ),
    AgentCatalogEntry(
        provider="zhipu-glm",
        provider_display_name="Zhipu GLM",
        runtime="claude-code-cli",
        runtime_display_name="Claude Code compatible runtime",
        models=("glm-5.2",),
        recommended_model="glm-5.2",
        tier="ADVANCED",
    ),
    AgentCatalogEntry(
        provider="moonshot-kimi",
        provider_display_name="Moonshot Kimi",
        runtime="claude-code-cli",
        runtime_display_name="Claude Code compatible runtime",
        models=("kimi-k2.5",),
        recommended_model="kimi-k2.5",
        tier="ADVANCED",
    ),
)


def catalog_entry(*, runtime: str, provider: str) -> AgentCatalogEntry | None:
    return next(
        (
            entry
            for entry in AGENT_CATALOG
            if entry.runtime == runtime and entry.provider == provider
        ),
        None,
    )


def ensure_supported(
    *,
    runtime: str,
    provider: str,
    authentication_mode: str,
    is_development_substitute: bool,
    model: str | None = None,
) -> None:
    """Raise `UnsupportedProviderConfiguration` for any combination this system does
    not know how to run — never fall back to a nearby-looking combination."""
    compatibility = RUNTIME_COMPATIBILITY.get(runtime)
    if compatibility is None:
        raise UnsupportedProviderConfiguration(f"unknown agent runtime: {runtime!r}")
    if provider not in compatibility.providers:
        raise UnsupportedProviderConfiguration(
            f"runtime {runtime!r} does not support provider {provider!r} "
            f"(supported: {sorted(compatibility.providers)!r})"
        )
    if authentication_mode not in compatibility.authentication_modes:
        raise UnsupportedProviderConfiguration(
            f"runtime {runtime!r} does not support authentication_mode "
            f"{authentication_mode!r} "
            f"(supported: {sorted(compatibility.authentication_modes)!r})"
        )
    if authentication_mode == "LOCAL_SESSION" and provider != compatibility.local_session_provider:
        raise UnsupportedProviderConfiguration(
            "LOCAL_SESSION (a mounted subscription session) can only authenticate "
            f"runtime {runtime!r}'s own provider "
            f"{compatibility.local_session_provider!r}, not {provider!r}"
        )
    if is_development_substitute != compatibility.is_development_substitute:
        raise UnsupportedProviderConfiguration(
            f"runtime {runtime!r} must have is_development_substitute="
            f"{compatibility.is_development_substitute!r}"
        )
    if not is_development_substitute and model is not None:
        entry = catalog_entry(runtime=runtime, provider=provider)
        if entry is None or model not in entry.models:
            allowed = list(entry.models) if entry else []
            raise UnsupportedProviderConfiguration(
                f"model {model!r} is not in the reviewed catalog for "
                f"runtime {runtime!r} and provider {provider!r} "
                f"(supported: {allowed!r})"
            )
