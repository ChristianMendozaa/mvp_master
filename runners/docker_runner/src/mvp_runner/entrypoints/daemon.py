import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import docker
import httpx
from mvp_common.contracts import SecretReference
from mvp_common.logging import configure_logging

from mvp_runner.adapters.agent_registry import EGRESS_REQUIRED_RUNTIMES
from mvp_runner.adapters.control_client import (
    ModelCredentialClient,
    RunnerControlClient,
    RunnerIdentity,
    SourceCredentialClient,
)
from mvp_runner.adapters.docker_agent import DockerAgentExecutor
from mvp_runner.adapters.docker_validator import DockerValidator
from mvp_runner.adapters.egress_network import EgressNetworkManager
from mvp_runner.adapters.leased_secret_resolver import LeasedSecretResolver
from mvp_runner.adapters.provider_catalog import allowlisted_hosts
from mvp_runner.adapters.workspace import LocalWorkspaceManager
from mvp_runner.domain.models import ValidationCommand
from mvp_runner.settings import Settings

LOGGER = logging.getLogger(__name__)


async def git(
    workspace: Path,
    *arguments: str,
    metadata: Path | None = None,
    credential: dict[str, str] | None = None,
) -> str:
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "GIT_AUTHOR_NAME": "MVP Master Agent",
        "GIT_AUTHOR_EMAIL": "agent@mvp-master.invalid",
        "GIT_COMMITTER_NAME": "MVP Master Agent",
        "GIT_COMMITTER_EMAIL": "agent@mvp-master.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
    askpass_root: Path | None = None
    if credential:
        askpass_root = Path(tempfile.mkdtemp(prefix="mvp-git-askpass-"))
        askpass = askpass_root / "askpass"
        askpass.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *Username*) printf '%s' \"$MVP_GIT_USERNAME\" ;;\n"
            "  *) printf '%s' \"$MVP_GIT_TOKEN\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        environment.update(
            {
                "GIT_ASKPASS": str(askpass),
                "MVP_GIT_USERNAME": credential["username"],
                "MVP_GIT_TOKEN": credential["token"],
            }
        )
    command = ["git"]
    if metadata is None:
        command.extend(["-C", str(workspace)])
    else:
        command.extend(["--git-dir", str(metadata), "--work-tree", str(workspace)])
    command.extend(arguments)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace")[-4000:])
        return stdout.decode().strip()
    finally:
        if askpass_root:
            await asyncio.to_thread(shutil.rmtree, askpass_root)


def ensure_repository_has_content(workspace: Path) -> None:
    if not any(path.name != ".git" for path in workspace.iterdir()):
        (workspace / ".mvp-empty-repository").write_text(
            "Isolated workspace initialized by MVP Master.\n",
            encoding="utf-8",
        )


def prepare_provider_probe_workspace(workspace: Path, runtime: str) -> None:
    if runtime != "deterministic":
        return
    fixture = workspace / "src" / "status.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        json.dumps({"title": "Provider probe", "status": "Pending"}) + "\n",
        encoding="utf-8",
    )


async def initialize_repository(workspace: Path) -> None:
    await git(workspace, "init", "--initial-branch=main")
    await asyncio.to_thread(ensure_repository_has_content, workspace)
    await git(workspace, "add", "--all")
    await git(workspace, "commit", "-m", "chore: initialize isolated fixture")


async def clone_repository(
    *,
    workspace: Path,
    metadata: Path,
    credential: dict[str, str],
) -> str:
    await asyncio.to_thread(workspace.rmdir)
    await git(
        workspace.parent,
        "clone",
        "--no-recurse-submodules",
        "--single-branch",
        "--branch",
        credential["default_branch"],
        "--separate-git-dir",
        str(metadata),
        credential["clone_locator"],
        str(workspace),
        credential=credential,
    )
    await git(workspace, "config", "core.hooksPath", os.devnull, metadata=metadata)
    return await git(workspace, "rev-parse", "HEAD", metadata=metadata)


async def run_job(
    job: dict[str, Any],
    *,
    settings: Settings,
    agent: DockerAgentExecutor,
    validator: DockerValidator,
    workspaces: LocalWorkspaceManager,
    identity: RunnerIdentity,
    control: RunnerControlClient,
    source: SourceCredentialClient,
    credentials: ModelCredentialClient,
    egress: EgressNetworkManager | None,
) -> dict[str, Any]:
    started = time.monotonic()
    execution_id = str(job["execution_id"])
    connected_repository = bool(job.get("repository_connection_id"))
    metadata: Path | None = None
    source_credential: dict[str, str] | None = None
    if connected_repository:
        capability = await control.source_capability(identity, str(job["job_id"]), "CHECKOUT_READ")
        source_credential = await source.exchange(capability)
        connected_repository = source_credential.get("development_substitute") != "true"
    if connected_repository and source_credential:
        workspace, metadata = await workspaces.provision_empty(execution_id)
        base_sha = await clone_repository(
            workspace=workspace, metadata=metadata, credential=source_credential
        )
    else:
        workspace = await workspaces.provision(execution_id)
        base_sha = ""
    exchange = settings.workspace_root / f"{execution_id}-exchange"
    exchange.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        if not connected_repository:
            await initialize_repository(workspace)
        (exchange / "input.json").write_text(
            json.dumps(job, separators=(",", ":")), encoding="utf-8"
        )
        model_environment: dict[str, str] = {}
        secret_reference_payload = job.get("secret_reference")
        if str(job.get("authentication_mode", "")) == "API_KEY_REFERENCE" and (
            secret_reference_payload
        ):
            # Resolved here, on the host, before the job container exists — never
            # inside it. See `adapters/leased_secret_resolver.py`. The job payload
            # written to `exchange/input.json` above still carries only the
            # *reference*; this value is never added to `job` or to any file.
            resolver = LeasedSecretResolver(
                identity=identity,
                job_id=str(job["job_id"]),
                control=control,
                credentials=credentials,
            )
            secret_value = await resolver.resolve(SecretReference(**secret_reference_payload))
            model_environment["MVP_MODEL_CREDENTIAL"] = secret_value
        egress_network: str | None = None
        runtime = str(job.get("runtime", ""))
        if runtime in EGRESS_REQUIRED_RUNTIMES:
            if egress is None:
                # `settings.agent_egress_enabled` is False on this runner. Fail
                # loudly rather than silently launching a real-agent runtime with
                # no network — see docs/adrs/0009-scoped-model-provider-egress.md.
                raise RuntimeError(
                    f"runtime {runtime!r} requires agent egress, which is disabled "
                    "on this runner (AGENT_EGRESS_ENABLED=false)"
                )
            proxy_url = await egress.ensure()
            # Both casings: not every CLI/runtime honors the same convention (some
            # check only uppercase, some only lowercase) — verified empirically
            # against a tinyproxy CONNECT proxy that busybox wget needed both
            # `http_proxy` and `https_proxy` set even for an HTTPS request.
            for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                model_environment[name] = proxy_url
            model_environment["NO_PROXY"] = model_environment["no_proxy"] = ""
            egress_network = settings.agent_egress_network
        agent_result = await agent.execute(
            workspace=workspace,
            exchange=exchange,
            timeout_seconds=int(job["max_duration_seconds"]),
            environment=model_environment,
            network=egress_network,
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
            await git(workspace, "add", "--all", metadata=metadata)
            changed_paths = (
                await git(workspace, "diff", "--cached", "--name-only", metadata=metadata)
            ).splitlines()
            if any(path.startswith(".github/workflows/") for path in changed_paths):
                raise RuntimeError("changes to GitHub workflow files are not permitted")
            await git(
                workspace,
                "commit",
                "-m",
                f"feat: implement approved work item\n\nExecution: {execution_id}",
                metadata=metadata,
            )
            if connected_repository and metadata and source_credential:
                for _ in range(2):
                    capability = await control.source_capability(
                        identity, str(job["job_id"]), "CHECKOUT_READ"
                    )
                    read_credential = await source.exchange(capability)
                    await git(
                        workspace,
                        "fetch",
                        "--no-tags",
                        "origin",
                        read_credential["default_branch"],
                        metadata=metadata,
                        credential=read_credential,
                    )
                    remote_sha = await git(
                        workspace,
                        "rev-parse",
                        f"origin/{read_credential['default_branch']}",
                        metadata=metadata,
                    )
                    if remote_sha == base_sha:
                        break
                    await git(
                        workspace,
                        "rebase",
                        f"origin/{read_credential['default_branch']}",
                        metadata=metadata,
                    )
                    validation = await validator.validate(workspace=workspace, commands=commands)
                    if not validation.passed:
                        raise RuntimeError("validation failed after rebasing onto the latest base")
                    base_sha = remote_sha
                capability = await control.source_capability(
                    identity, str(job["job_id"]), "PUBLISH_WRITE"
                )
                write_credential = await source.exchange(capability)
                branch = f"mvp-master/executions/{execution_id}"
                await git(
                    workspace,
                    "push",
                    "origin",
                    f"HEAD:refs/heads/{branch}",
                    metadata=metadata,
                    credential=write_credential,
                )
            commit_sha = await git(workspace, "rev-parse", "HEAD", metadata=metadata)
            patch = await git(
                workspace,
                "format-patch",
                "-1",
                "--stdout",
                "HEAD",
                metadata=metadata,
            )
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
                "session_id": agent_result.get("session_id"),
                "input_tokens": agent_result.get("input_tokens"),
                "cached_input_tokens": agent_result.get("cached_input_tokens"),
                "output_tokens": agent_result.get("output_tokens"),
                "events": [
                    {
                        "sequence": int(event["sequence"]),
                        "kind": str(event["kind"]),
                        "name": str(event["name"]),
                        "message": str(event["message"]),
                        "metadata": dict(event.get("metadata") or {}),
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
    source: SourceCredentialClient,
    credentials: ModelCredentialClient,
    egress: EgressNetworkManager | None,
) -> dict[str, Any]:
    task = asyncio.create_task(
        run_job(
            job,
            settings=settings,
            agent=agent,
            validator=validator,
            workspaces=workspaces,
            identity=identity,
            control=control,
            source=source,
            credentials=credentials,
            egress=egress,
        )
    )
    while True:
        done, _ = await asyncio.wait({task}, timeout=10)
        if task in done:
            return await task
        await control.heartbeat_job(identity, str(job["job_id"]))


async def run_provider_verification(
    verification: dict[str, Any],
    *,
    settings: Settings,
    agent: DockerAgentExecutor,
    workspaces: LocalWorkspaceManager,
    identity: RunnerIdentity,
    control: RunnerControlClient,
    credentials: ModelCredentialClient,
    egress: EgressNetworkManager | None,
) -> dict[str, Any]:
    """Exercise the exact runtime/model/auth path without a repository or delivery."""
    verification_id = str(verification["verification_id"])
    workspace, _ = await workspaces.provision_empty(verification_id)
    exchange = settings.workspace_root / f"{verification_id}-probe-exchange"
    exchange.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        runtime = str(verification["runtime"])
        await asyncio.to_thread(prepare_provider_probe_workspace, workspace, runtime)
        await initialize_repository(workspace)
        environment: dict[str, str] = {}
        if str(verification.get("authentication_mode")) == "API_KEY_REFERENCE":
            capability = await control.provider_verification_model_capability(
                identity, verification_id
            )
            secret_value = await credentials.exchange(capability)
            environment["MVP_MODEL_CREDENTIAL"] = secret_value
        network: str | None = None
        if runtime in EGRESS_REQUIRED_RUNTIMES:
            if egress is None:
                raise RuntimeError("scoped provider egress is disabled on this runner")
            proxy_url = await egress.ensure()
            for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                environment[name] = proxy_url
            environment["NO_PROXY"] = environment["no_proxy"] = ""
            network = settings.agent_egress_network
        payload = {
            **verification,
            "execution_id": verification_id,
            "title": "Provider connection verification",
            "problem": (
                "Confirm this coding-agent connection. Return a short READY response "
                "and do not modify repository files."
            ),
            "acceptance_criteria": ["Provider authentication succeeds"],
        }
        (exchange / "input.json").write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        result = await agent.execute(
            workspace=workspace,
            exchange=exchange,
            timeout_seconds=int(verification["max_duration_seconds"]),
            environment=environment,
            network=network,
        )
        return {
            "success": bool(result["success"]),
            "summary": (
                "Provider connection verified."
                if result["success"]
                else "Provider connection could not be verified."
            ),
            "input_tokens": result.get("input_tokens"),
            "cached_input_tokens": result.get("cached_input_tokens"),
            "output_tokens": result.get("output_tokens"),
        }
    finally:
        await workspaces.cleanup(verification_id)
        if exchange.exists():
            for child in exchange.iterdir():
                child.unlink()
            exchange.rmdir()


async def run_provider_verification_with_heartbeat(
    verification: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    identity = kwargs["identity"]
    control = kwargs["control"]
    task = asyncio.create_task(run_provider_verification(verification, **kwargs))
    while True:
        done, _ = await asyncio.wait({task}, timeout=10)
        if task in done:
            return await task
        await control.heartbeat_provider_verification(
            identity, str(verification["verification_id"])
        )


async def main() -> None:
    configure_logging()
    settings = Settings()
    identity = RunnerIdentity(runner_id=settings.runner_id, credential=settings.runner_credential)
    workspaces = LocalWorkspaceManager(settings.workspace_root, settings.fixture_path)
    agent = DockerAgentExecutor(settings.job_image)
    validator = DockerValidator(image=settings.job_image)
    egress: EgressNetworkManager | None = None
    if settings.agent_egress_enabled:
        egress = EgressNetworkManager(
            docker.from_env(),
            network_name=settings.agent_egress_network,
            proxy_container_name=f"{settings.agent_egress_network}-proxy",
            proxy_image=settings.agent_egress_proxy_image,
            proxy_port=settings.agent_egress_proxy_port,
            allowed_hosts=allowlisted_hosts(),
            config_root=settings.workspace_root / "egress-proxy-config",
        )
        # Fail fast at startup rather than on the first job that needs it.
        await egress.ensure()
    async with httpx.AsyncClient() as http_client:
        control = RunnerControlClient(settings.delivery_url, http_client)
        source = SourceCredentialClient(settings.integrations_url, http_client)
        credentials = ModelCredentialClient(settings.integrations_url, http_client)
        while True:
            try:
                job = await control.lease_job(identity)
                if job is None:
                    verification = await control.lease_provider_verification(identity)
                    if verification is None:
                        await asyncio.sleep(settings.poll_seconds)
                        continue
                    try:
                        verification_result = await run_provider_verification_with_heartbeat(
                            verification,
                            settings=settings,
                            agent=agent,
                            workspaces=workspaces,
                            identity=identity,
                            control=control,
                            credentials=credentials,
                            egress=egress,
                        )
                    except Exception:
                        LOGGER.exception("provider verification failed")
                        verification_result = {
                            "success": False,
                            "summary": ("Provider verification failed inside the isolated runner."),
                            "input_tokens": None,
                            "cached_input_tokens": None,
                            "output_tokens": None,
                        }
                    await control.complete_provider_verification(
                        identity,
                        str(verification["verification_id"]),
                        verification_result,
                    )
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
                        source=source,
                        credentials=credentials,
                        egress=egress,
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
