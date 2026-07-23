import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from mvp_common.contracts import SecretReference

from mvp_runner.adapters.codex_cli import CodexCliAgent
from mvp_runner.adapters.deterministic_agent import DeterministicAgent
from mvp_runner.application.ports import AgentRuntime
from mvp_runner.domain.models import AgentRequest


async def run(input_path: Path, output_path: Path) -> None:
    payload = json.loads(await asyncio.to_thread(input_path.read_text, encoding="utf-8"))
    runtime = str(payload["runtime"])
    agents: dict[str, AgentRuntime] = {
        "deterministic": cast(AgentRuntime, DeterministicAgent()),
        "codex-cli": cast(AgentRuntime, CodexCliAgent()),
    }
    if runtime not in agents:
        raise RuntimeError(f"unsupported agent runtime: {runtime}")
    reference_payload = payload.get("secret_reference")
    reference = SecretReference(**reference_payload) if reference_payload else None
    request = AgentRequest(
        execution_id=UUID(str(payload["execution_id"])),
        organization_id=UUID(str(payload["organization_id"])),
        model=str(payload["model"]),
        authentication_mode=str(payload["authentication_mode"]),
        secret_reference=reference,
        workspace=PurePosixPath("/workspace"),
        title=str(payload["title"]),
        problem=str(payload["problem"]),
        acceptance_criteria=tuple(str(item) for item in payload["acceptance_criteria"]),
        max_turns=int(payload["max_turns"]),
        max_duration_seconds=int(payload["max_duration_seconds"]),
    )
    result = await agents[runtime].execute(request)
    await asyncio.to_thread(
        output_path.write_text,
        json.dumps(asdict(result), default=str, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]), Path(sys.argv[2])))
