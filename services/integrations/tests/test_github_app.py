import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from mvp_integrations.adapters.github import GitHubAppClient


async def test_manifest_conversion_keeps_credentials_at_adapter_boundary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app-manifests/temporary-code/conversions"
        return httpx.Response(
            201,
            json={
                "id": 123,
                "client_id": "Iv1.synthetic",
                "client_secret": "synthetic-client-secret",
                "pem": "synthetic-private-key",
                "webhook_secret": "synthetic-webhook-secret",
                "slug": "mvp-master-test",
            },
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await GitHubAppClient(client=client, api_version="2026-03-10").convert_manifest(
            "temporary-code"
        )

    assert result.app_id == "123"
    assert result.pem == b"synthetic-private-key"
    assert result.webhook_secret == b"synthetic-webhook-secret"


async def test_installation_token_is_restricted_to_repository_and_permissions() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app/installations/456/access_tokens"
        authorization = request.headers["authorization"].removeprefix("Bearer ")
        claims = jwt.decode(
            authorization,
            private_key.public_key(),
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        assert claims["iss"] == "123"
        assert request.read() == (b'{"repository_ids":[789],"permissions":{"contents":"read"}}')
        return httpx.Response(
            201,
            json={"token": "ghs_synthetic", "expires_at": "2026-07-25T13:00:00Z"},
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        credential = await GitHubAppClient(
            client=client, api_version="2026-03-10"
        ).installation_token(
            installation_id="456",
            app_id="123",
            private_key=pem,
            repository_id="789",
            permissions={"contents": "read"},
        )

    assert credential.token == "ghs_synthetic"
