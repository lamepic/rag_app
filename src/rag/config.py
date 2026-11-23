import functools
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, SecretStr
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

    # Supabase Storage through its S3-compatible API. Keys: `supabase status` (S3_PROTOCOL_*).
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr
    s3_region: str = "local"
    storage_bucket: str = "papers"
    max_upload_bytes: int = 50 * 1024 * 1024

    @property
    def _supabase_base(self) -> str:
        return str(self.supabase_url).rstrip("/")

    @property
    def jwt_issuer(self) -> str:
        """The `iss` claim Supabase Auth puts in every access token."""
        return f"{self._supabase_base}/auth/v1"

    @property
    def jwks_url(self) -> str:
        """Where Supabase Auth publishes the public keys that verify its tokens."""
        return f"{self.jwt_issuer}/.well-known/jwks.json"

    @property
    def s3_endpoint_url(self) -> str:
        return f"{self._supabase_base}/storage/v1/s3"


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
