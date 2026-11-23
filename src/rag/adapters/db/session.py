from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rag.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """One engine (connection pool) per app. Creating it doesn't connect yet."""
    return create_async_engine(str(settings.database_url), pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
