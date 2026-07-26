"""Integration coverage for the controlled-egress mechanism (Phase 3).

Requires a reachable Docker daemon — same requirement as `make test-integration`.
Deliberately does not depend on live internet access to any real provider: the
"allowed" case points at a hostname that is in the allowlist but does not resolve,
so it fails at the connection stage (proving the proxy let it *through* the
filter); the "denied" case points at a hostname that is *not* in the allowlist, so
tinyproxy rejects it with `403 Filtered` before ever attempting to connect. The
distinction between those two failure modes is the thing under test, not whether a
particular external host happens to be reachable from CI.
"""

import uuid
from pathlib import Path

import docker
import docker.errors
import pytest
from mvp_runner.adapters.egress_network import EgressNetworkManager

pytestmark = pytest.mark.integration


@pytest.fixture
def docker_client() -> docker.DockerClient:
    client = docker.from_env()
    try:
        client.ping()
    except Exception as error:
        pytest.skip(f"no reachable Docker daemon: {error}")
    return client


def _run_and_capture(
    client: docker.DockerClient, *, network: str, environment: dict[str, str], target: str
) -> bytes:
    try:
        return bytes(
            client.containers.run(
                "alpine:latest",
                ["wget", "-T", "5", "-q", "-O-", target],
                network=network,
                environment=environment,
                remove=True,
                stderr=True,
            )
        )
    except docker.errors.ContainerError as error:
        return bytes(error.stderr or b"")


async def test_egress_network_allows_listed_host_and_denies_others(
    docker_client: docker.DockerClient, tmp_path: Path
) -> None:
    suffix = uuid.uuid4().hex[:8]
    network_name = f"mvpm-test-egress-{suffix}"
    proxy_name = f"{network_name}-proxy"
    manager = EgressNetworkManager(
        docker_client,
        network_name=network_name,
        proxy_container_name=proxy_name,
        proxy_image="vimagick/tinyproxy",
        proxy_port=3128,
        allowed_hosts=("allowed.invalid",),
        config_root=tmp_path,
    )
    try:
        proxy_url = await manager.ensure()
        assert proxy_url == f"http://{proxy_name}:3128"
        proxy_env = {"https_proxy": proxy_url, "http_proxy": proxy_url}

        denied_output = _run_and_capture(
            docker_client,
            network=network_name,
            environment=proxy_env,
            target="https://denied.invalid",
        )
        assert b"Filtered" in denied_output

        allowed_output = _run_and_capture(
            docker_client,
            network=network_name,
            environment=proxy_env,
            target="https://allowed.invalid",
        )
        # The allowed host doesn't resolve, so the proxy fails to *connect* — the
        # assertion that matters is that it's a different failure than the filter
        # denial above, i.e. the filter let it through.
        assert b"Filtered" not in allowed_output

        no_route_output = _run_and_capture(
            docker_client,
            network=network_name,
            environment={},
            target="https://allowed.invalid",
        )
        assert no_route_output != b""
        assert b"Filtered" not in no_route_output
    finally:
        await manager.teardown()
