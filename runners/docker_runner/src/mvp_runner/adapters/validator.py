import asyncio
import time
from pathlib import Path

from mvp_runner.domain.models import (
    ValidationCommand,
    ValidationEvidence,
    ValidationResult,
)

MAX_CAPTURE_BYTES = 64 * 1024


class SubprocessValidator:
    """Test adapter. Production execution uses the same contract in a fresh container."""

    def __init__(self, validator_image: str = "host-test-adapter") -> None:
        self._validator_image = validator_image

    async def validate(
        self, *, workspace: Path, commands: tuple[ValidationCommand, ...]
    ) -> ValidationResult:
        evidence: list[ValidationEvidence] = []
        passed = True
        for command in commands:
            started = time.monotonic()
            process = await asyncio.create_subprocess_exec(
                command.executable,
                *command.arguments,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "CI": "true"},
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=command.timeout_seconds
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                stdout, stderr = b"", b"validator command timed out"
            duration_ms = int((time.monotonic() - started) * 1000)
            exit_code = process.returncode if process.returncode is not None else 124
            evidence.append(
                ValidationEvidence(
                    executable=command.executable,
                    arguments=command.arguments,
                    exit_code=exit_code,
                    stdout=stdout[-MAX_CAPTURE_BYTES:].decode(errors="replace"),
                    stderr=stderr[-MAX_CAPTURE_BYTES:].decode(errors="replace"),
                    duration_ms=duration_ms,
                )
            )
            if exit_code != 0:
                passed = False
                break
        return ValidationResult(
            passed=passed,
            validator_image=self._validator_image,
            evidence=tuple(evidence),
        )
