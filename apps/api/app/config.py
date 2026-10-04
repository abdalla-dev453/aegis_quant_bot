from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://onyx:onyx@127.0.0.1:5432/onyx"
    redis_url: str = "redis://127.0.0.1:6379/0"
    web_origin: str = "http://localhost:3000"
    session_cookie_name: str = "aegis_session"
    session_cookie_secure: bool = True
    session_ttl_seconds: int = Field(default=43_200, ge=300, le=2_592_000)
    pairing_code_ttl_seconds: int = Field(default=600, ge=60, le=3_600)
    signal_ttl_seconds: int = Field(default=30, ge=1, le=300)
    request_max_age_seconds: int = Field(default=30, ge=1, le=30)
    nonce_ttl_seconds: int = Field(default=60, ge=30, le=300)
    ea_rate_limit_per_minute: int = Field(default=120, ge=1, le=10_000)
    app_rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()