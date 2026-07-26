import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from uuid import UUID

from mvp_common.contracts import SecretReference

from mvp_runner.adapters.agent_registry import SUPPORTED_RUNTIMES, build_agents
from mvp_runner.adapters.provider_catalog import endpoint_for
from mvp_runner.domain.errors import (
    UnknownProvider,
    UnsupportedAuthenticationMode,
    UnsupportedRuntime,
)
from mvp_runner.domain.models import AgentEvent, AgentEventKind, AgentRequest, AgentResult


async def run(input_path: Path, output_path: Path) -> None:
    payload = json.loads(await asyncio.to_thread(input_path.read_text, encoding="utf-8"))
    reference_payload = payload.get("secret_reference")
    reference = SecretReference(**reference_payload) if reference_payload else None
    request = AgentRequest(
        execution_id=UUID(str(payload["execution_id"])),
        organization_id=UUID(str(payload["organization_id"])),
        provider=str(payload.get("provider", "local")),
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
    runtime = str(payload["runtime"])
    # The already-resolved secret (if any) was injected as an env var by the host-side
    # daemon before this container was launched — see
    # `entrypoints/daemon.py::run_job` and `adapters/leased_secret_resolver.py`. This
    # process never resolves a `SecretReference` itself, and the value is removed from
    # the environment (`pop`, not `get`) so no child process of a *different* runtime
    # accidentally inherits it.
    secret = os.environ.pop("MVP_MODEL_CREDENTIAL", None)

    result = await _execute(runtime=runtime, request=request, secret=secret)
    await asyncio.to_thread(
        output_path.write_text,
        json.dumps(asdict(result), default=str, separators=(",", ":")),
        encoding="utf-8",
    )


async def _execute(*, runtime: str, request: AgentRequest, secret: str | None) -> AgentResult:
    """Select the agent, enforce capability compatibility, and run it.

    Failures that are data-driven (an unknown provider/runtime, or a job whose
    authentication_mode the selected runtime does not support) are reported as a
    normalized failed `AgentResult` with an `ERROR` event, not an unhandled
    exception — the job still completes (and the container exits 0), so delivery
    sees a clear, attributable failure instead of a generic "job container failed"
    message from a crashed process.
    """
    try:
        endpoint = endpoint_for(request.provider)
        if runtime not in SUPPORTED_RUNTIMES:
            raise UnsupportedRuntime(f"unsupported agent runtime: {runtime!r}")
        agents = build_agents(secret=secret, endpoint=endpoint)
        agent = agents[runtime]
        capabilities = await agent.capabilities()
        if request.authentication_mode not in capabilities.supported_authentication_modes:
            raise UnsupportedAuthenticationMode(
                f"runtime {runtime!r} does not support authentication_mode "
                f"{request.authentication_mode!r} (supports "
                f"{capabilities.supported_authentication_modes!r})"
            )
    except (UnknownProvider, UnsupportedRuntime, UnsupportedAuthenticationMode) as error:
        return _failed_result(error)
    return await agent.execute(request)


def _failed_result(error: Exception) -> AgentResult:
    return AgentResult(
        success=False,
        summary="The isolated runner job could not start: the requested runtime "
        "configuration is not supported.",
        session_id=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        turns=0,
        changed_paths=(),
        events=(
            AgentEvent(
                sequence=1,
                kind=AgentEventKind.ERROR,
                name=f"runtime.{type(error).__name__.lower()}",
                message=str(error),
            ),
        ),
    )


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]), Path(sys.argv[2])))
