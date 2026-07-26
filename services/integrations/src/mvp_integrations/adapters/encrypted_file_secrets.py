import asyncio
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from mvp_common.contracts import SecretReference


class EncryptedFileSecretStore:
    """Self-hosted secret store whose callers persist references, never values."""

    def __init__(self, root: Path, master_key_file: Path) -> None:
        self._root = root.resolve()
        key = master_key_file.read_bytes()
        if len(key) != 32:
            raise ValueError("secret master key must contain exactly 32 bytes")
        self._cipher = AESGCM(key)

    def _path(self, reference: SecretReference) -> Path:
        if reference.store != "encrypted-file":
            raise ValueError("unsupported secret store")
        parts = (*reference.namespace.split("/"), reference.key)
        if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
            raise ValueError("secret reference contains an unsafe path")
        candidate = self._root.joinpath(*parts).with_suffix(".json").resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("secret reference escaped configured root")
        return candidate

    @staticmethod
    def _aad(reference: SecretReference) -> bytes:
        return (
            f"{reference.store}:{reference.namespace}:{reference.key}:{reference.version or ''}"
        ).encode()

    async def put(self, reference: SecretReference, value: bytes) -> None:
        path = self._path(reference)
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, value, self._aad(reference))
        document = json.dumps(
            {"version": 1, "nonce": nonce.hex(), "ciphertext": ciphertext.hex()},
            separators=(",", ":"),
        ).encode()

        def write() -> None:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(document)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                if temporary.exists():
                    temporary.unlink()

        await asyncio.to_thread(write)

    async def get(self, reference: SecretReference) -> bytes:
        path = self._path(reference)

        def read() -> bytes:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("version") != 1:
                raise ValueError("unsupported encrypted secret version")
            return self._cipher.decrypt(
                bytes.fromhex(str(document["nonce"])),
                bytes.fromhex(str(document["ciphertext"])),
                self._aad(reference),
            )

        return await asyncio.to_thread(read)

    async def delete(self, reference: SecretReference) -> None:
        await asyncio.to_thread(self._path(reference).unlink, missing_ok=True)
