"""GET /v1/me: the HTTP side of auth (status codes and headers)."""

import uuid

import httpx
import pytest

from tests.tokens import FakeJWKSServer
from tests.unit.conftest import AuthHeaders


async def test_valid_token_returns_the_user(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    user_id = uuid.uuid4()

    response = await client.get("/v1/me", headers=auth_headers(user_id, email="ada@example.com"))

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
    client: httpx.AsyncClient, auth_headers: AuthHeaders, jwks_server: FakeJWKSServer
) -> None:
    jwks_server.fail = True
    response = await client.get("/v1/me", headers=auth_headers())
    assert response.status_code == 503
