"""FastAPI application factory.

Run with: uvicorn rag.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from rag.adapters.auth.jwks import JWKSTokenVerifier
from rag.adapters.db.session import create_engine, create_sessionmaker
from rag.adapters.storage.s3 import S3BlobStore, create_s3_client
from rag.api.routes import collections, documents, health, me
from rag.config import Settings, get_settings

MiB = 1024 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a new app. Tests pass their own settings; production uses the environment."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        http = httpx.AsyncClient(timeout=5.0)
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.token_verifier = JWKSTokenVerifier(
            jwks_url=settings.jwks_url,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            http=http,
        )
        app.state.blob_store = S3BlobStore(create_s3_client(settings), settings.storage_bucket)
        yield
        await http.aclose()
        await engine.dispose()

    # Body limits are enforced while the body streams in, so an oversized request is cut
    # off early instead of being spooled to disk first. JSON endpoints get 1 MiB; the
    # document routes allow a full upload plus room for the multipart framing.
    app = FastAPI(title=settings.app_name, lifespan=lifespan, max_body_size=MiB)
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(collections.router)
    app.include_router(documents.router, max_body_size=settings.max_upload_bytes + MiB)
    return app
