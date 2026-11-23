"""GET /v1/me: the HTTP side of auth (status codes and headers)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from rag.adapters.auth.jwks import JWKSTokenVerifier
from rag.api.deps import get_token_verifier
from rag.config import Settings
from rag.main import create_app
from tests.tokens import AUDIENCE, ISSUER, JWKS_URL, FakeJWKSServer, TokenSigner


@pytest.fixture
def signer() -> TokenSigner:
    return TokenSigner()


@pytest.fixture
def server(signer: TokenSigner) -> FakeJWKSServer:
    return FakeJWKSServer(signer)


@pytest.fixture
async def client(settings: Settings, server: FakeJWKSServer) -> AsyncIterator[httpx.AsyncClient]:
    async with server.client() as jwks_http:
        verifier = JWKSTokenVerifier(
            jwks_url=JWKS_URL, issuer=ISSUER, audience=AUDIENCE, http=jwks_http
        )
        app = create_app(settings)
        app.dependency_overrides[get_token_verifier] = lambda: verifier

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_valid_token_returns_the_user(client: httpx.AsyncClient, signer: TokenSigner) -> None:
    user_id = uuid.uuid4()
    token = signer.token(sub=str(user_id), email="ada@example.com")

    response = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"id": str(user_id), "email": "ada@example.com"}


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-header"),
        pytest.param({"Authorization": "Bearer not-a-jwt"}, id="garbage-token"),
        pytest.param({"Authorization": "Basic dXNlcjpwYXNz"}, id="wrong-scheme"),
    ],
)
async def test_missing_or_bad_token_is_401(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/v1/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_unreachable_auth_server_is_503(
    client: httpx.AsyncClient, signer: TokenSigner, server: FakeJWKSServer
) -> None:
    server.fail = True
    response = await client.get("/v1/me", headers={"Authorization": f"Bearer {signer.token()}"})
    assert response.status_code == 503
