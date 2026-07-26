"""Per-runner-process egress proxy for real (non-deterministic) agent runtimes.

Job containers are launched with `network_disabled=True` by default (see
`adapters/docker_agent.py`) — the `deterministic` runtime and the validator
container always stay that way, unconditionally. Runtimes that must call a real
model API instead join a dedicated Docker network created here, with
`internal=True`: Docker installs no NAT/masquerade rule for an internal network, so
a container on it has no route off the host *at all* except through the proxy
container also attached to it. That is the fail-closed property this design relies
on — a client that ignores `HTTPS_PROXY` does not silently reach the internet, it
simply cannot connect anywhere.

The proxy's allowlist comes only from `provider_catalog.allowlisted_hosts()` —
never from tenant input, since a tenant-supplied base URL would be an SSRF /
secret-exfiltration vector (the resolved model credential is sent to whatever host
is configured). The proxy does not terminate TLS: it only allows or denies the
CONNECT method to specific hostnames on port 443, so provider traffic stays
end-to-end encrypted between the agent process and the real provider.

Verified empirically (`docker network create --internal ...` + a tinyproxy
container attached to both that network and the default bridge): a container on
the internal network alone cannot resolve or reach any host; through the proxy, an
allowlisted host succeeds and a non-allowlisted host is rejected by tinyproxy
itself with `403 Filtered`, before ever leaving the proxy container.
"""

import asyncio
import contextlib
from pathlib import Path

import docker
from docker.errors import NotFound

_TINYPROXY_CONF_TEMPLATE = """\
User nobody
Group nobody
Port {port}
Timeout 30
DisableViaHeader Yes
Filter "/etc/tinyproxy/filter"
FilterDefaultDeny Yes
ConnectPort 443
"""


class EgressNetworkManager:
    def __init__(
        self,
        client: docker.DockerClient,
        *,
        network_name: str,
        proxy_container_name: str,
        proxy_image: str,
        proxy_port: int,
        allowed_hosts: tuple[str, ...],
        config_root: Path,
    ) -> None:
        self._client = client
        self._network_name = network_name
        self._proxy_container_name = proxy_container_name
        self._proxy_image = proxy_image
        self._proxy_port = proxy_port
        self._allowed_hosts = allowed_hosts
        self._config_root = config_root

    async def ensure(self) -> str:
        """Idempotently create the internal network and start the proxy container.

        Returns the proxy URL (e.g. `http://mvp-agent-egress-proxy:3128`) that job
        containers on `network_name` can reach via that network's embedded DNS.
        """
        return await asyncio.to_thread(self._ensure_sync)

    async def teardown(self) -> None:
        await asyncio.to_thread(self._teardown_sync)

    def _ensure_sync(self) -> str:
        self._ensure_network()
        self._write_proxy_config()
        self._ensure_proxy_container()
        return f"http://{self._proxy_container_name}:{self._proxy_port}"

    def _ensure_network(self) -> None:
        try:
            self._client.networks.get(self._network_name)
        except NotFound:
            self._client.networks.create(self._network_name, driver="bridge", internal=True)

    def _write_proxy_config(self) -> None:
        self._config_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self._config_root / "tinyproxy.conf").write_text(
            _TINYPROXY_CONF_TEMPLATE.format(port=self._proxy_port), encoding="utf-8"
        )
        # One hostname per line; tinyproxy's Filter matches these with
        # FilterDefaultDeny Yes, so anything not listed here is rejected with a
        # `403 Filtered` response before the CONNECT ever reaches the real host.
        (self._config_root / "filter").write_text(
            "\n".join(self._allowed_hosts) + "\n", encoding="utf-8"
        )

    def _ensure_proxy_container(self) -> None:
        try:
            container = self._client.containers.get(self._proxy_container_name)
            if container.status != "running":
                container.start()
            return
        except NotFound:
            pass
        container = self._client.containers.run(
            self._proxy_image,
            name=self._proxy_container_name,
            volumes={
                str(self._config_root / "tinyproxy.conf"): {
                    "bind": "/etc/tinyproxy/tinyproxy.conf",
                    "mode": "ro",
                },
                str(self._config_root / "filter"): {
                    "bind": "/etc/tinyproxy/filter",
                    "mode": "ro",
                },
            },
            restart_policy={"Name": "unless-stopped"},
            detach=True,
        )
        self._client.networks.get(self._network_name).connect(container)

    def _teardown_sync(self) -> None:
        with contextlib.suppress(NotFound):
            self._client.containers.get(self._proxy_container_name).remove(force=True)
        with contextlib.suppress(NotFound):
            self._client.networks.get(self._network_name).remove()
