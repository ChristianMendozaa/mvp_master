import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from mvp_runner.adapters.deterministic_agent import DeterministicAgent
from mvp_runner.adapters.validator import SubprocessValidator
from mvp_runner.adapters.workspace import LocalWorkspaceManager
from mvp_runner.application.execute import RunnerExecutionService
from mvp_runner.domain.errors import UnsupportedAuthenticationMode, UnsupportedRuntime
from mvp_runner.domain.models import ValidationCommand
from mvp_runner.entrypoints.daemon import (
    failed_job_result,
    initialize_repository,
    prepare_provider_probe_workspace,
)


async def test_deterministic_agent_is_independently_validated(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "src" / "status.json").write_text(
        json.dumps({"title": "Old", "status": "Pending"}), encoding="utf-8"
    )
    (fixture / "verify.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "data=json.loads(Path('src/status.json').read_text())\n"
        "assert data['status'] == 'Delivered by deterministic local agent'\n",
        encoding="utf-8",
    )
    service = RunnerExecutionService(
        agents={"deterministic": DeterministicAgent()},
        validator=SubprocessValidator(),
        workspaces=LocalWorkspaceManager(tmp_path / "workspaces", fixture),
    )
    result, validation = await service.execute(
        execution_id=uuid4(),
        organization_id=uuid4(),
        runtime="deterministic",
        provider="local",
        model="deterministic-v1",
        authentication_mode="NONE",
        secret_reference=None,
        title="Delivery status",
        problem="The delivery state is unclear.",
        acceptance_criteria=("The status is visible.",),
        max_turns=2,
        max_duration_seconds=30,
        validation_commands=(ValidationCommand(sys.executable, ("verify.py",), 10),),
    )
    assert result.success
    assert validation.passed
    assert validation.evidence[0].exit_code == 0


async def test_unsupported_authentication_mode_is_rejected_before_execute(
    tmp_path: Path,
) -> None:
    """Regression test for the systemic fix: an auth mode the selected runtime does
    not advertise in `capabilities()` must be rejected at the composition root,
    before `agent.execute()` ever runs — this is what used to crash `CodexCliAgent`
    with an unhandled `RuntimeError`."""
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    service = RunnerExecutionService(
        agents={"deterministic": DeterministicAgent()},
        validator=SubprocessValidator(),
        workspaces=LocalWorkspaceManager(tmp_path / "workspaces", fixture),
    )
    with pytest.raises(UnsupportedAuthenticationMode):
        await service.execute(
            execution_id=uuid4(),
            organization_id=uuid4(),
            runtime="deterministic",
            provider="local",
            model="deterministic-v1",
            authentication_mode="API_KEY_REFERENCE",
            secret_reference=None,
            title="Delivery status",
            problem="The delivery state is unclear.",
            acceptance_criteria=("The status is visible.",),
            max_turns=2,
            max_duration_seconds=30,
            validation_commands=(),
        )


async def test_unknown_runtime_raises_unsupported_runtime(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    service = RunnerExecutionService(
        agents={"deterministic": DeterministicAgent()},
        validator=SubprocessValidator(),
        workspaces=LocalWorkspaceManager(tmp_path / "workspaces", fixture),
    )
    with pytest.raises(UnsupportedRuntime):
        await service.execute(
            execution_id=uuid4(),
            organization_id=uuid4(),
            runtime="not-a-real-runtime",
            provider="local",
            model="deterministic-v1",
            authentication_mode="NONE",
            secret_reference=None,
            title="Delivery status",
            problem="The delivery state is unclear.",
            acceptance_criteria=("The status is visible.",),
            max_turns=2,
            max_duration_seconds=30,
            validation_commands=(),
        )


async def test_workspace_rejects_path_traversal(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    manager = LocalWorkspaceManager(tmp_path / "workspaces", fixture)
    with pytest.raises(ValueError):
        await manager.provision("../escape")


async def test_empty_probe_workspace_can_be_initialized(tmp_path: Path) -> None:
    workspace = tmp_path / "probe"
    workspace.mkdir()

    await initialize_repository(workspace)

    assert (workspace / ".mvp-empty-repository").is_file()


def test_deterministic_provider_probe_gets_synthetic_fixture(tmp_path: Path) -> None:
    prepare_provider_probe_workspace(tmp_path, "deterministic")

    fixture = json.loads((tmp_path / "src" / "status.json").read_text())
    assert fixture == {"title": "Provider probe", "status": "Pending"}


def test_failed_job_result_is_bounded_and_does_not_expose_error_message() -> None:
    result = failed_job_result(
        RuntimeError("credential must not be returned"), job_image="runner@sha256:test"
    )
    assert result["agent"]["success"] is False
    assert result["validation"]["passed"] is False
    assert "credential" not in json.dumps(result)
