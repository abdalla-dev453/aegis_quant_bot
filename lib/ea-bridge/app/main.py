from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis, from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.errors import APIError, api_error_handler, validation_error_handler
from app.routes.app import router as app_router
from app.routes.ea import router as ea_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = from_url(str(settings.redis_url), decode_responses=True)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis
    app.state.settings = settings

    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AegisQuant API",
        version="1.0.0",
        description="Instrument-Grade MT5 EA Bridge and AI Quantitative Trading Backend",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    app.include_router(ea_router)
    app.include_router(app_router)

    @app.get("/healthz", tags=["observability"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["observability"])
    async def readyz(request: Request) -> dict[str, str]:
        # Readiness only succeeds when both persistent dependencies are reachable.
        redis: Redis = request.app.state.redis
        await redis.ping()
        async with request.app.state.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
