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

    async def cleanup(self, execution_id: str) -> None:
        path = self._path(execution_id)
        if path.exists():
            await asyncio.to_thread(shutil.rmtree, path)
