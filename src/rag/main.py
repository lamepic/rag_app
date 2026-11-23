"""FastAPI application factory.

Run with: uvicorn rag.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rag.adapters.db.session import create_engine, create_sessionmaker
from rag.api.routes import health
from rag.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a new app. Tests pass their own settings; production uses the environment."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.sessionmaker = create_sessionmaker(engine)
        yield
        await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    return app
