import functools
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_")

    app_name: str = "rag"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: PostgresDsn
    redis_url: RedisDsn

    # Supabase API gateway (Auth and Storage live behind it).
    supabase_url: AnyHttpUrl
    jwt_audience: str = "authenticated"

    @property
    def jwt_issuer(self) -> str:
        """The `iss` claim Supabase Auth puts in every access token."""
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        """Where Supabase Auth publishes the public keys that verify its tokens."""
        return f"{self.jwt_issuer}/.well-known/jwks.json"


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
