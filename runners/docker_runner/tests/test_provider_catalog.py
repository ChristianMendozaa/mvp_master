import pytest
from mvp_runner.adapters.provider_catalog import (
    PROVIDER_CATALOG,
    ProviderAuthStyle,
    allowlisted_hosts,
    endpoint_for,
    environment_for,
)
from mvp_runner.domain.errors import UnknownProvider


def test_endpoint_for_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProvider):
        endpoint_for("not-a-real-provider")


def test_endpoint_for_known_providers() -> None:
    assert endpoint_for("anthropic").auth_style is ProviderAuthStyle.ANTHROPIC_API_KEY
    assert endpoint_for("openai").auth_style is ProviderAuthStyle.OPENAI_API_KEY
    zhipu = endpoint_for("zhipu-glm")
    assert zhipu.base_url == "https://open.bigmodel.cn/api/anthropic"
    assert zhipu.auth_style is ProviderAuthStyle.ANTHROPIC_AUTH_TOKEN
    kimi = endpoint_for("moonshot-kimi")
    assert kimi.base_url == "https://api.moonshot.ai/anthropic"


def test_environment_for_none_auth_style_ignores_secret() -> None:
    endpoint = endpoint_for("local")
    assert environment_for(endpoint, None) == {}
    assert environment_for(endpoint, "unused-secret") == {}


def test_environment_for_anthropic_api_key() -> None:
    endpoint = endpoint_for("anthropic")
    environment = environment_for(endpoint, "sk-ant-test")
    assert environment == {"ANTHROPIC_API_KEY": "sk-ant-test"}
    assert "ANTHROPIC_BASE_URL" not in environment


def test_environment_for_compatible_endpoint_sets_base_url_and_auth_token() -> None:
    endpoint = endpoint_for("zhipu-glm")
    environment = environment_for(endpoint, "zhipu-secret")
    assert environment == {
        "ANTHROPIC_AUTH_TOKEN": "zhipu-secret",
        "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    }
    # Never falls back to ANTHROPIC_API_KEY for a third-party endpoint.
    assert "ANTHROPIC_API_KEY" not in environment


def test_environment_for_requires_secret_when_auth_style_is_not_none() -> None:
    endpoint = endpoint_for("anthropic")
    with pytest.raises(ValueError, match="requires a resolved secret"):
        environment_for(endpoint, None)


def test_allowlisted_hosts_has_no_duplicates_schemes_or_ports() -> None:
    hosts = allowlisted_hosts()
    assert len(hosts) == len(set(hosts))
    for host in hosts:
        assert "://" not in host
        assert ":" not in host


def test_catalog_entries_are_internally_consistent() -> None:
    for provider, endpoint in PROVIDER_CATALOG.items():
        assert endpoint.provider == provider
        if endpoint.auth_style is ProviderAuthStyle.NONE:
            assert endpoint.egress_hosts == ()
        else:
            assert endpoint.egress_hosts, f"{provider} needs network but has no egress_hosts"
