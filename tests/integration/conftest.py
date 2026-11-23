"""Fixtures for tests that talk to the real local Supabase."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from rag.config import Settings


@pytest.fixture
async def db_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back.

    join_transaction_mode="create_savepoint" turns the code's own commit() and
    rollback() calls into savepoints, so the outer transaction stays in control
    and the test leaves nothing behind, even after a commit or an IntegrityError.
    """
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
