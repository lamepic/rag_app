"""FastAPI application factory.

Run with: uvicorn rag.main:create_app --factory
"""

from fastapi import FastAPI

from rag.api.routes import health
from rag.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a new app. Tests pass their own settings; production uses the environment."""
    settings = settings or get_settings()

    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.include_router(health.router)
    return app
