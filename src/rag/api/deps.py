"""Shared FastAPI dependencies.

Each one reads a long-lived object from app.state (built in the app's lifespan).
Tests swap them out with app.dependency_overrides.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rag.core.auth import AuthUnavailableError, CurrentUser, InvalidTokenError, TokenVerifier
from rag.core.storage import BlobStore


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Uncommitted work is rolled back when it closes."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_blob_store(request: Request) -> BlobStore:
    store: BlobStore = request.app.state.blob_store
    return store


BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store)]


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


# auto_error=False: we raise our own 401 instead of FastAPI's default response.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        return await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        # Deliberately vague: telling a caller *why* a token failed helps attackers.
        raise _unauthorized("Invalid token") from exc
    except AuthUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth unavailable") from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def _unauthorized(detail: str) -> HTTPException:
    # RFC 6750: a 401 must tell the client which auth scheme to use.
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )
