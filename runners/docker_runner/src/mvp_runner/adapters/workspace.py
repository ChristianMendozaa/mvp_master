import asyncio
import shutil
from pathlib import Path


class LocalWorkspaceManager:
    def __init__(self, root: Path, fixture: Path) -> None:
        self._root = root.resolve()
        self._fixture = fixture.resolve()

    def _path(self, execution_id: str) -> Path:
        safe_characters = "abcdefghijklmnopqrstuvwxyz0123456789-"
        if not execution_id or any(
            character not in safe_characters for character in execution_id.lower()
        ):
            raise ValueError("execution ID contains unsafe path characters")
        candidate = (self._root / execution_id).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("workspace escaped configured root")
        return candidate

    async def provision(self, execution_id: str) -> Path:
        path = self._path(execution_id)
        if path.exists():
            await asyncio.to_thread(shutil.rmtree, path)
        await asyncio.to_thread(shutil.copytree, self._fixture, path, symlinks=False)
        return path

    async def provision_empty(self, execution_id: str) -> tuple[Path, Path]:
        path = self._path(execution_id)
        metadata = self._path(f"{execution_id}-git")
        for candidate in (path, metadata):
            if candidate.exists():
                await asyncio.to_thread(shutil.rmtree, candidate)
        await asyncio.to_thread(path.mkdir, mode=0o700, parents=True)
        return path, metadata

    async def cleanup(self, execution_id: str) -> None:
        for path in (self._path(execution_id), self._path(f"{execution_id}-git")):
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
