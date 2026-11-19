import functools
from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_")

    app_name: str = "rag"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: PostgresDsn
    redis_url: RedisDsn


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
