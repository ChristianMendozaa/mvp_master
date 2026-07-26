import os
from pathlib import Path

import pytest
from mvp_common.contracts import SecretReference
from mvp_integrations.adapters.encrypted_file_secrets import EncryptedFileSecretStore


async def test_encrypted_file_store_round_trips_without_plaintext(tmp_path: Path) -> None:
    key_file = tmp_path / "master.key"
    key_file.write_bytes(os.urandom(32))
    store = EncryptedFileSecretStore(tmp_path / "values", key_file)
    reference = SecretReference(
        store="encrypted-file",
        namespace="github-app/configuration",
        key="private-key",
    )

    await store.put(reference, b"synthetic-private-value")

    stored = (tmp_path / "values/github-app/configuration/private-key.json").read_bytes()
    assert b"synthetic-private-value" not in stored
    assert await store.get(reference) == b"synthetic-private-value"
    await store.delete(reference)
    assert not (tmp_path / "values/github-app/configuration/private-key.json").exists()


async def test_encrypted_file_store_rejects_traversal(tmp_path: Path) -> None:
    key_file = tmp_path / "master.key"
    key_file.write_bytes(os.urandom(32))
    store = EncryptedFileSecretStore(tmp_path / "values", key_file)
    reference = SecretReference(
        store="encrypted-file",
        namespace="../outside",
        key="secret",
    )

    with pytest.raises(ValueError, match="unsafe path"):
        await store.put(reference, b"value")
