import asyncio
import json
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
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._execute_sync, workspace, exchange, timeout_seconds)

    def _execute_sync(
        self, workspace: Path, exchange: Path, timeout_seconds: int
    ) -> dict[str, Any]:
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
            network_disabled=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit="768m",
            nano_cpus=1_000_000_000,
            pids_limit=128,
            user="10001:10001",
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},  # noqa: S108
            detach=True,
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
