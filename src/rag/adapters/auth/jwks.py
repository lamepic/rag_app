"""Verify JWTs against a JWKS endpoint (Supabase Auth publishes one).

The auth server signs tokens with its private key and publishes the public half
as a JWKS. We fetch that, cache it, and check each token's signature locally:
no network call per request, and no shared secret in our config.
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import jwt

from rag.core.auth import AuthUnavailableError, CurrentUser, InvalidTokenError

# Asymmetric algorithms only. Never HS256 (that needs a shared secret) and never "none".
ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})


class JWKSTokenVerifier:
    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        http: httpx.AsyncClient,
        cache_ttl: float = 600.0,
        min_refresh_interval: float = 30.0,
        leeway: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._http = http
        self._cache_ttl = cache_ttl
        self._min_refresh_interval = min_refresh_interval
        self._leeway = leeway
        self._clock = clock

        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> CurrentUser:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("malformed token") from exc

        kid = header.get("kid")
        if not isinstance(kid, str):
            raise InvalidTokenError("token has no key id")

        key = await self._get_key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                # The algorithm comes from OUR copy of the key, never from the token's
                # header: trusting the header is the classic "algorithm confusion" attack.
                algorithms=[key.algorithm_name],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        try:
            user_id = uuid.UUID(claims["sub"])
        except (ValueError, TypeError) as exc:
            raise InvalidTokenError("sub is not a user id") from exc

        email = claims.get("email")
        return CurrentUser(id=user_id, email=email if isinstance(email, str) else None)

    async def _get_key(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys or self._cache_expired():
            async with self._lock:
                # Re-check inside the lock: a concurrent request may have just refreshed.
                # An unknown kid usually means the server rotated keys, so refetch, but at
                # most every min_refresh_interval, or random kids would let anyone make us
                # hammer the auth server.
                if self._cache_expired() or (kid not in self._keys and self._may_refresh()):
                    await self._refresh()

        key = self._keys.get(kid)
        if key is None:
            raise InvalidTokenError("unknown signing key")
        return key

    def _cache_expired(self) -> bool:
        return self._fetched_at is None or self._clock() - self._fetched_at >= self._cache_ttl

    def _may_refresh(self) -> bool:
        return (
            self._fetched_at is None
            or self._clock() - self._fetched_at >= self._min_refresh_interval
        )

    async def _refresh(self) -> None:
        try:
            response = await self._http.get(self._jwks_url)
            response.raise_for_status()
            jwks = jwt.PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            raise AuthUnavailableError(f"could not load signing keys: {exc}") from exc

        self._keys = {
            key.key_id: key
            for key in jwks.keys
            if key.key_id is not None and key.algorithm_name in ALLOWED_ALGORITHMS
        }
        self._fetched_at = self._clock()
