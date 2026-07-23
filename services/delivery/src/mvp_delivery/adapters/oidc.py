import asyncio
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from mvp_delivery.settings import Settings


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str


class PrincipalProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwk_client = PyJWKClient(settings.oidc_jwks_url, cache_jwk_set=True, lifespan=300)

    async def authenticate(
        self,
        authorization: str | None = Header(default=None),
        x_development_subject: str | None = Header(default=None),
    ) -> Principal:
        if self._settings.allow_development_identity and x_development_subject:
            return Principal(subject=x_development_subject)
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="a bearer access token is required")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            key = await asyncio.to_thread(self._jwk_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as error:
            raise HTTPException(status_code=401, detail="access token is invalid") from error
        return Principal(subject=str(claims["sub"]))
