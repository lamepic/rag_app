"""Shared test fixtures. Tests never read the developer's .env file."""

from pathlib import Path

import pytest

from rag.config import Settings

INTEGRATION_DIR = Path(__file__).parent / "integration"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/integration/ gets the `integration` marker automatically."""
    for item in items:
        if INTEGRATION_DIR in item.path.parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres",
        redis_url="redis://127.0.0.1:6379/0",
        supabase_url="http://127.0.0.1:54321",
        s3_access_key_id="unit-test-key-id",
        s3_secret_access_key="unit-test-secret",
    )
