"""POST and GET /v1/collections."""

import uuid

import httpx
import pytest

from tests.fakes import InMemoryUnitOfWork
from tests.unit.conftest import AuthHeaders


async def test_create_returns_201_and_commits(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, uow: InMemoryUnitOfWork
) -> None:
    response = await client.post(
        "/v1/collections",
        json={"name": "  Thesis  ", "description": "protein folding"},
        headers=auth_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Thesis"  # surrounding whitespace is stripped
    assert body["description"] == "protein folding"
    assert uuid.UUID(body["id"])
    assert "owner_id" not in body  # internal: the caller already knows who they are
    assert uow.commits == 1


async def test_duplicate_name_is_409_and_not_committed(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, uow: InMemoryUnitOfWork
) -> None:
    headers = auth_headers(uuid.uuid4())
    await client.post("/v1/collections", json={"name": "Thesis"}, headers=headers)

    response = await client.post("/v1/collections", json={"name": "Thesis"}, headers=headers)

    assert response.status_code == 409
    assert uow.commits == 1  # only the first create


async def test_two_users_can_use_the_same_name(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    for _ in range(2):
        response = await client.post(
            "/v1/collections", json={"name": "Thesis"}, headers=auth_headers()
        )
        assert response.status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="no-name"),
        pytest.param({"name": "   "}, id="blank-name"),
        pytest.param({"name": "x" * 201}, id="name-too-long"),
        pytest.param({"name": "ok", "owner_id": str(uuid.uuid4())}, id="unknown-field"),
    ],
)
async def test_invalid_body_is_422(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, body: dict[str, object]
) -> None:
    response = await client.post("/v1/collections", json=body, headers=auth_headers())
    assert response.status_code == 422


async def test_list_shows_only_my_collections_newest_first(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    me, someone_else = auth_headers(uuid.uuid4()), auth_headers(uuid.uuid4())
    await client.post("/v1/collections", json={"name": "first"}, headers=me)
    await client.post("/v1/collections", json={"name": "second"}, headers=me)
    await client.post("/v1/collections", json={"name": "not mine"}, headers=someone_else)

    response = await client.get("/v1/collections", headers=me)

    assert response.status_code == 200
    assert [c["name"] for c in response.json()["items"]] == ["second", "first"]


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_requires_auth(client: httpx.AsyncClient, method: str) -> None:
    response = await client.request(method, "/v1/collections", json={"name": "x"})
    assert response.status_code == 401
