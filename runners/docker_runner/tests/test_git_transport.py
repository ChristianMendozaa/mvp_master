from pathlib import Path

from mvp_runner.entrypoints.daemon import clone_repository, git


async def test_git_metadata_stays_outside_agent_workspace(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    await git(seed, "init", "--initial-branch=main")
    (seed / "README.md").write_text("synthetic repository\n", encoding="utf-8")
    await git(seed, "add", "--all")
    await git(seed, "commit", "-m", "initial")

    remote = tmp_path / "remote.git"
    await git(tmp_path, "clone", "--bare", str(seed), str(remote))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    metadata = tmp_path / "trusted-git-metadata"

    base_sha = await clone_repository(
        workspace=workspace,
        metadata=metadata,
        credential={
            "clone_locator": remote.as_uri(),
            "default_branch": "main",
            "username": "x-access-token",
            "token": "synthetic-ephemeral-token",
        },
    )

    assert len(base_sha) == 40
    assert metadata.is_dir()
    assert (workspace / ".git").is_file()
    assert (workspace / "README.md").read_text(encoding="utf-8") == ("synthetic repository\n")
