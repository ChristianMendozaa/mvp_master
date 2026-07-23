import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from mvp_common.logging import configure_logging

from mvp_runner.adapters.control_client import RunnerControlClient, RunnerIdentity
from mvp_runner.adapters.docker_agent import DockerAgentExecutor
from mvp_runner.adapters.docker_validator import DockerValidator
from mvp_runner.adapters.workspace import LocalWorkspaceManager
from mvp_runner.domain.models import ValidationCommand
from mvp_runner.settings import Settings

LOGGER = logging.getLogger(__name__)


async def git(workspace: Path, *arguments: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(workspace),
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "MVP Master Agent",
            "GIT_AUTHOR_EMAIL": "agent@mvp-master.invalid",
            "GIT_COMMITTER_NAME": "MVP Master Agent",
            "GIT_COMMITTER_EMAIL": "agent@mvp-master.invalid",
        },
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    return stdout.decode().strip()


async def initialize_repository(workspace: Path) -> None:
    await git(workspace, "init", "--initial-branch=main")
    await git(workspace, "add", "--all")
    await git(workspace, "commit", "-m", "chore: initialize isolated fixture")


async def run_job(
    job: dict[str, Any],
    *,
    settings: Settings,
    agent: DockerAgentExecutor,
    validator: DockerValidator,
    workspaces: LocalWorkspaceManager,
) -> dict[str, Any]:
    started = time.monotonic()
    execution_id = str(job["execution_id"])
    workspace = await workspaces.provision(execution_id)
    exchange = settings.workspace_root / f"{execution_id}-exchange"
    exchange.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        await initialize_repository(workspace)
        (exchange / "input.json").write_text(
            json.dumps(job, separators=(",", ":")), encoding="utf-8"
        )
        agent_result = await agent.execute(
            workspace=workspace,
            exchange=exchange,
            timeout_seconds=int(job["max_duration_seconds"]),
        )
        commands = tuple(
            ValidationCommand(
                executable=str(item["executable"]),
                arguments=tuple(str(value) for value in item["arguments"]),
                timeout_seconds=int(item["timeout_seconds"]),
            )
            for item in job["validation_commands"]
        )
        validation = await validator.validate(workspace=workspace, commands=commands)
        commit_sha = "0" * 40
        patch = ""
        if bool(agent_result["success"]) and validation.passed:
            await git(workspace, "add", "--all")
            await git(
                workspace,
                "commit",
                "-m",
                f"feat: implement approved work item\n\nExecution: {execution_id}",
            )
            commit_sha = await git(workspace, "rev-parse", "HEAD")
            patch = await git(workspace, "format-patch", "-1", "--stdout", "HEAD")
        return {
            "commit_sha": commit_sha,
            "patch": patch[-131072:],
            "duration_seconds": int(time.monotonic() - started),
            "cost_minor": 0,
            "agent": {
                "success": bool(agent_result["success"]),
                "summary": str(agent_result["summary"]),
                "turns": int(agent_result["turns"]),
                "changed_paths": list(agent_result["changed_paths"]),
                "events": [
                    {
                        "sequence": int(event["sequence"]),
                        "kind": str(event["kind"]),
                        "name": str(event["name"]),
                        "message": str(event["message"]),
                    }
                    for event in agent_result["events"]
                ],
            },
            "validation": {
                "passed": validation.passed,
                "validator_image": validation.validator_image,
                "evidence": [
                    {
                        "executable": item.executable,
                        "arguments": list(item.arguments),
                        "exit_code": item.exit_code,
                        "stdout": item.stdout,
                        "stderr": item.stderr,
                        "duration_ms": item.duration_ms,
                    }
                    for item in validation.evidence
                ],
            },
        }
    finally:
        await workspaces.cleanup(execution_id)
        for child in exchange.iterdir():
            child.unlink()
        exchange.rmdir()


def failed_job_result(error: Exception, *, job_image: str) -> dict[str, Any]:
    error_name = type(error).__name__
    return {
        "commit_sha": "0" * 40,
        "patch": "",
        "duration_seconds": 0,
        "cost_minor": 0,
        "agent": {
            "success": False,
            "summary": "The isolated runner job failed before independent verification.",
            "turns": 0,
            "changed_paths": [],
            "events": [
                {
                    "sequence": 1,
                    "kind": "ERROR",
                    "name": "runner.job_failed",
                    "message": (
                        f"Runner job failed with {error_name}; details remain in runner logs."
                    ),
                }
            ],
        },
        "validation": {
            "passed": False,
            "validator_image": job_image,
            "evidence": [],
        },
    }


async def run_with_heartbeat(
    job: dict[str, Any],
    *,
    identity: RunnerIdentity,
    control: RunnerControlClient,
    settings: Settings,
    agent: DockerAgentExecutor,
    validator: DockerValidator,
    workspaces: LocalWorkspaceManager,
) -> dict[str, Any]:
    task = asyncio.create_task(
        run_job(
            job,
            settings=settings,
            agent=agent,
            validator=validator,
            workspaces=workspaces,
        )
    )
    while True:
        done, _ = await asyncio.wait({task}, timeout=10)
        if task in done:
            return await task
        await control.heartbeat_job(identity, str(job["job_id"]))


async def main() -> None:
    configure_logging()
    settings = Settings()
    identity = RunnerIdentity(runner_id=settings.runner_id, credential=settings.runner_credential)
    workspaces = LocalWorkspaceManager(settings.workspace_root, settings.fixture_path)
    agent = DockerAgentExecutor(settings.job_image)
    validator = DockerValidator(image=settings.job_image)
    async with httpx.AsyncClient() as http_client:
        control = RunnerControlClient(settings.delivery_url, http_client)
        while True:
            try:
                job = await control.lease_job(identity)
                if job is None:
                    await asyncio.sleep(settings.poll_seconds)
                    continue
                try:
                    result = await run_with_heartbeat(
                        job,
                        identity=identity,
                        control=control,
                        settings=settings,
                        agent=agent,
                        validator=validator,
                        workspaces=workspaces,
                    )
                except Exception as error:
                    LOGGER.exception("isolated runner job failed")
                    result = failed_job_result(error, job_image=settings.job_image)
                await control.complete_job(identity, str(job["job_id"]), result)
            except Exception:
                LOGGER.exception("runner iteration failed")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
