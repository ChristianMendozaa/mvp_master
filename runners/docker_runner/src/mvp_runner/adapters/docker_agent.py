import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import docker


class DockerAgentExecutor:
    def __init__(self, image: str) -> None:
        self._image = image
        self._client = docker.from_env()

    async def execute(
        self,
        *,
        workspace: Path,
        exchange: Path,
        timeout_seconds: int,
        environment: Mapping[str, str] | None = None,
        network: str | None = None,
    ) -> dict[str, Any]:
        """Launch the job container.

        `environment` carries only already-resolved values (a model credential
        injected by `daemon.py::run_job`, egress proxy variables) — never a
        `SecretReference`. It becomes the container's *entire* environment (merged
        with nothing from this process' own `os.environ`), so nothing the daemon
        itself has in its environment leaks into the sandboxed job by accident.

        `network` is `None` for every runtime that does not call a real model API
        (in particular `deterministic`, always) — the container gets
        `network_disabled=True` and no route anywhere. When a runtime does need to
        reach a provider, `network` names the `internal=True` egress network set up
        by `adapters/egress_network.py`, and `network_disabled` is omitted entirely
        (never pass both — see docs/adrs/0009-scoped-model-provider-egress.md).
        """
        return await asyncio.to_thread(
            self._execute_sync, workspace, exchange, timeout_seconds, environment or {}, network
        )

    def _execute_sync(
        self,
        workspace: Path,
        exchange: Path,
        timeout_seconds: int,
        environment: Mapping[str, str],
        network: str | None,
    ) -> dict[str, Any]:
        network_kwargs: dict[str, Any] = (
            {"network": network} if network is not None else {"network_disabled": True}
        )
        container = self._client.containers.run(
            self._image,
            [
                "python",
                "-m",
                "mvp_runner.entrypoints.job",
                "/job/input.json",
                "/job/output.json",
            ],
            volumes={
                str(workspace): {"bind": "/workspace", "mode": "rw"},
                str(exchange): {"bind": "/job", "mode": "rw"},
            },
            environment=dict(environment),
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit="768m",
            nano_cpus=1_000_000_000,
            pids_limit=128,
            user="10001:10001",
            tmpfs={
                "/tmp": "rw,noexec,nosuid,size=64m",  # noqa: S108
                # Writable HOME for CLI-driven agents (npm/claude/codex config and
                # cache). Deliberately *not* noexec: some CLIs extract and execute
                # helper binaries from their cache directory. See
                # docs/threat-model.md for this documented deviation. `uid`/`gid`/
                # `mode` are required — verified empirically that a bare `rw` tmpfs
                # mounts root-owned `0755` and the non-root job user cannot write to
                # it at all without these.
                "/home/app": "rw,nosuid,size=256m,uid=10001,gid=10001,mode=0700",
            },
            detach=True,
            **network_kwargs,
        )
        try:
            result = container.wait(timeout=timeout_seconds)
            if int(result["StatusCode"]) != 0:
                logs = container.logs().decode(errors="replace")[-4000:]
                raise RuntimeError(f"agent job container failed: {logs}")
            return cast(
                dict[str, Any],
                json.loads((exchange / "output.json").read_text(encoding="utf-8")),
            )
        finally:
            container.remove(force=True)
