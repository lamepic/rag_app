"""Shared test fixtures. Tests never read the developer's .env file."""

import pytest

from rag.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres",
        redis_url="redis://127.0.0.1:6379/0",
    )
