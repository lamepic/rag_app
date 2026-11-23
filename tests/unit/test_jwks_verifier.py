"""JWKSTokenVerifier: which tokens pass, which fail, and when keys are fetched."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest

from rag.adapters.auth.jwks import JWKSTokenVerifier
from rag.core.auth import AuthUnavailableError, InvalidTokenError
from tests.tokens import AUDIENCE, ISSUER, JWKS_URL, FakeClock, FakeJWKSServer, TokenSigner


@pytest.fixture
def signer() -> TokenSigner:
    return TokenSigner()


@pytest.fixture
def server(signer: TokenSigner) -> FakeJWKSServer:
    return FakeJWKSServer(signer)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def verifier(server: FakeJWKSServer, clock: FakeClock) -> AsyncIterator[JWKSTokenVerifier]:
    async with server.client() as http:
        yield JWKSTokenVerifier(
            jwks_url=JWKS_URL,
            issuer=ISSUER,
            audience=AUDIENCE,
            http=http,
            cache_ttl=600,
            min_refresh_interval=30,
            clock=clock,
        )


# --- tokens that pass -------------------------------------------------------------------


async def test_valid_token_returns_the_user(
    verifier: JWKSTokenVerifier, signer: TokenSigner
) -> None:
    user_id = uuid.uuid4()
    user = await verifier.verify(signer.token(sub=str(user_id), email="ada@example.com"))

    assert user.id == user_id
    assert user.email == "ada@example.com"


async def test_recently_expired_token_passes_within_leeway(
    verifier: JWKSTokenVerifier, signer: TokenSigner
) -> None:
    await verifier.verify(signer.token(expires_in=-5))  # leeway is 10s, for clock skew


# --- tokens that fail -------------------------------------------------------------------


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"expires_in": -60}, id="expired"),
        pytest.param({"aud": "someone-else"}, id="wrong-audience"),
        pytest.param({"iss": "https://evil.example/auth/v1"}, id="wrong-issuer"),
        pytest.param({"sub": None}, id="no-sub"),
        pytest.param({"exp": None}, id="no-exp"),
        pytest.param({"sub": "not-a-uuid"}, id="sub-not-uuid"),
    ],
)
async def test_bad_claims_are_rejected(
    verifier: JWKSTokenVerifier, signer: TokenSigner, claims: dict[str, Any]
) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(signer.token(**claims))


async def test_token_signed_by_another_key_is_rejected(verifier: JWKSTokenVerifier) -> None:
    forger = TokenSigner(kid="test-key")  # same kid, different private key
    with pytest.raises(InvalidTokenError):
        await verifier.verify(forger.token())


async def test_hs256_token_is_rejected(verifier: JWKSTokenVerifier) -> None:
    """Algorithm confusion: the token picks HS256, but we only accept the key's own alg."""
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": AUDIENCE, "iss": ISSUER, "exp": 9999999999, "iat": 0},
        "a-shared-secret-at-least-32-bytes-long",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
async def test_malformed_token_is_rejected(verifier: JWKSTokenVerifier, token: str) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


# --- when keys are fetched --------------------------------------------------------------


async def test_keys_are_cached_until_ttl(
    verifier: JWKSTokenVerifier, signer: TokenSigner, server: FakeJWKSServer, clock: FakeClock
) -> None:
    await verifier.verify(signer.token())
    await verifier.verify(signer.token())
    assert server.calls == 1

    clock.advance(601)
    await verifier.verify(signer.token())
    assert server.calls == 2


async def test_rotated_key_is_picked_up(
    verifier: JWKSTokenVerifier, signer: TokenSigner, server: FakeJWKSServer, clock: FakeClock
) -> None:
    await verifier.verify(signer.token())

    new_signer = TokenSigner(kid="rotated-key")
    server.signers.append(new_signer)
    clock.advance(31)

    await verifier.verify(new_signer.token())  # unknown kid -> refetch -> found
    assert server.calls == 2


async def test_unknown_kids_cannot_force_repeated_fetches(
    verifier: JWKSTokenVerifier, signer: TokenSigner, server: FakeJWKSServer
) -> None:
    await verifier.verify(signer.token())

    for i in range(5):
        with pytest.raises(InvalidTokenError):
            await verifier.verify(signer.token(kid=f"random-{i}"))

    assert server.calls == 1  # still within min_refresh_interval: no refetches


async def test_unreachable_jwks_is_auth_unavailable(
    verifier: JWKSTokenVerifier, signer: TokenSigner, server: FakeJWKSServer
) -> None:
    server.fail = True
    with pytest.raises(AuthUnavailableError):
        await verifier.verify(signer.token())
