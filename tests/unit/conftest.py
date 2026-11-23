"""An app wired with fakes, plus an HTTP client and a way to act as any user."""

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from rag.adapters.auth.jwks import JWKSTokenVerifier
from rag.api.deps import get_blob_store, get_token_verifier, get_uow
from rag.config import Settings
from rag.main import create_app
from tests.fakes import InMemoryBlobStore, InMemoryUnitOfWork
from tests.tokens import AUDIENCE, ISSUER, JWKS_URL, FakeJWKSServer, TokenSigner

AuthHeaders = Callable[..., dict[str, str]]


@pytest.fixture
def signer() -> TokenSigner:
    return TokenSigner()


@pytest.fixture
def jwks_server(signer: TokenSigner) -> FakeJWKSServer:
    return FakeJWKSServer(signer)


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def blobs() -> InMemoryBlobStore:
    return InMemoryBlobStore()


@pytest.fixture
async def app(
    settings: Settings,
    jwks_server: FakeJWKSServer,
    uow: InMemoryUnitOfWork,
    blobs: InMemoryBlobStore,
) -> AsyncIterator[FastAPI]:
    async with jwks_server.client() as jwks_http:
        verifier = JWKSTokenVerifier(
            jwks_url=JWKS_URL, issuer=ISSUER, audience=AUDIENCE, http=jwks_http
        )
        app = create_app(settings)
        app.dependency_overrides[get_token_verifier] = lambda: verifier
        app.dependency_overrides[get_uow] = lambda: uow
        app.dependency_overrides[get_blob_store] = lambda: blobs
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def auth_headers(signer: TokenSigner) -> AuthHeaders:
    """auth_headers() for a fresh user, auth_headers(user_id) to act as a specific one."""

    def make(user_id: uuid.UUID | None = None, **claims: Any) -> dict[str, str]:
        token = signer.token(sub=str(user_id or uuid.uuid4()), **claims)
        return {"Authorization": f"Bearer {token}"}

    return make
