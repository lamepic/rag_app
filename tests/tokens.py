"""Test doubles for auth: a key pair that signs tokens, a fake JWKS server and a fake clock."""

import time
import uuid
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

ISSUER = "http://127.0.0.1:54321/auth/v1"
AUDIENCE = "authenticated"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"


class TokenSigner:
    """Plays Supabase Auth: owns a private key, publishes the public half, signs tokens."""

    def __init__(self, kid: str = "test-key") -> None:
        self.kid = kid
        self._private_key = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict[str, Any]:
        public = ECAlgorithm.to_jwk(self._private_key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "alg": "ES256", "use": "sig"}

    def token(self, *, expires_in: int = 3600, kid: str | None = None, **claims: Any) -> str:
        """A valid token unless overridden. Pass a claim as None to leave it out."""
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": str(uuid.uuid4()),
            "email": "user@example.com",
            "role": "authenticated",
            "iat": now,
            "exp": now + expires_in,
        }
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(
            payload, self._private_key, algorithm="ES256", headers={"kid": kid or self.kid}
        )


class FakeJWKSServer:
    """Serves whatever keys it is given and counts how often it is asked."""

    def __init__(self, *signers: TokenSigner) -> None:
        self.signers = list(signers)
        self.calls = 0
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.fail:
            return httpx.Response(500)
        return httpx.Response(200, json={"keys": [s.jwk() for s in self.signers]})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
