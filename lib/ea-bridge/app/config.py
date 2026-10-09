from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
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

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value: object) -> str:
        """Hosted Postgres commonly supplies a sync URL; this app uses asyncpg."""
        url = str(value)
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        return url

    @field_validator("web_origin")
    @classmethod
    def validate_web_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            _port = parsed.port  # Validate the port syntax before accepting the origin.
        except ValueError as exc:
            raise ValueError("WEB_ORIGIN contains an invalid port") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("WEB_ORIGIN must be an origin URL without a path, query, or fragment")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @model_validator(mode="after")
    def require_secure_production_origin(self) -> "Settings":
        if self.app_env.lower() == "production":
            if not self.web_origin.startswith("https://"):
                raise ValueError("WEB_ORIGIN must use HTTPS in production")
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
