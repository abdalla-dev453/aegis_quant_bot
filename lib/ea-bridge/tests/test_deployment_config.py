from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgres://user:pass@db.example/app", "postgresql+asyncpg://user:pass@db.example/app"),
        (
            "postgresql://user:pass@db.example/app",
            "postgresql+asyncpg://user:pass@db.example/app",
        ),
        (
            "postgresql+asyncpg://user:pass@db.example/app",
            "postgresql+asyncpg://user:pass@db.example/app",
        ),
    ],
)
def test_hosted_postgres_urls_use_async_driver(database_url: str, expected: str) -> None:
    settings = Settings(database_url=database_url)
    assert settings.database_url == expected


def test_production_requires_https_origin_and_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="WEB_ORIGIN must use HTTPS"):
        Settings(app_env="production", web_origin="http://dashboard.example.com")

    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE must be true"):
        Settings(
            app_env="production",
            web_origin="https://dashboard.example.com",
            session_cookie_secure=False,
        )


def test_web_origin_rejects_path_components() -> None:
    with pytest.raises(ValidationError, match="without a path"):
        Settings(web_origin="https://dashboard.example.com/dashboard")
