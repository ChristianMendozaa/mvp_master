import asyncio
import time
from pathlib import Path

import docker

from mvp_runner.domain.models import (
    ValidationCommand,
    ValidationEvidence,
    ValidationResult,
)


class DockerValidator:
    def __init__(self, *, image: str) -> None:
        self._image = image
        self._client = docker.from_env()

    async def validate(
        self, *, workspace: Path, commands: tuple[ValidationCommand, ...]
    ) -> ValidationResult:
        return await asyncio.to_thread(self._validate_sync, workspace, commands)

    def _validate_sync(
        self, workspace: Path, commands: tuple[ValidationCommand, ...]
    ) -> ValidationResult:
        evidence: list[ValidationEvidence] = []
        passed = True
        for command in commands:
            started = time.monotonic()
            container = self._client.containers.run(
                self._image,
                [command.executable, *command.arguments],
                working_dir="/workspace",
                volumes={str(workspace): {"bind": "/workspace", "mode": "ro"}},
                network_disabled=True,
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="512m",
                nano_cpus=1_000_000_000,
                pids_limit=128,
                user="65532:65532",
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},  # noqa: S108
                detach=True,
            )
            try:
                result = container.wait(timeout=command.timeout_seconds)
                output = container.logs(stdout=True, stderr=False).decode(errors="replace")
                errors = container.logs(stdout=False, stderr=True).decode(errors="replace")
            finally:
                container.remove(force=True)
            exit_code = int(result["StatusCode"])
            evidence.append(
                ValidationEvidence(
                    executable=command.executable,
                    arguments=command.arguments,
                    exit_code=exit_code,
                    stdout=output[-65536:],
                    stderr=errors[-65536:],
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            if exit_code != 0:
                passed = False
                break
        return ValidationResult(
            passed=passed,
            validator_image=self._image,
            evidence=tuple(evidence),
        )
