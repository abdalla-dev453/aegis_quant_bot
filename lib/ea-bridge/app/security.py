from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.config import Settings, get_settings
from app.database import get_redis, get_session
from app.errors import APIError
from app.models import Device, User, UserSession

NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_ea_request(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    body_digest = hashlib.sha256(body).hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_digest}".encode()


def sign_ea_request(token: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    message = canonical_ea_request(method, path, timestamp, nonce, body)
    return hmac.new(token.encode("ascii"), message, hashlib.sha256).hexdigest()


async def enforce_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int = 60) -> None:
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception as exc:
        raise APIError(
            "rate_limiter_unavailable",
            "Request could not be safely rate limited",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if count > limit:
        raise APIError("rate_limited", "Request rate limit exceeded", status.HTTP_429_TOO_MANY_REQUESTS)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user: User
    session: UserSession


@dataclass(frozen=True, slots=True)
class AuthenticatedDevice:
    device: Device


async def get_current_user(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> AuthenticatedUser:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise APIError("unauthorized", "Authentication required", status.HTTP_401_UNAUTHORIZED)
    user_session = await session.scalar(
        select(UserSession).where(
            UserSession.token_hash == sha256_hex(raw_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    if user_session is None:
        raise APIError("unauthorized", "Session is invalid or expired", status.HTTP_401_UNAUTHORIZED)
    user = await session.get(User, user_session.user_id)
    if user is None or user.deleted_at is not None:
        raise APIError("unauthorized", "Session is invalid or expired", status.HTTP_401_UNAUTHORIZED)
    await enforce_rate_limit(redis, f"rate:user:{user.id}", settings.app_rate_limit_per_minute)
    return AuthenticatedUser(user=user, session=user_session)


async def get_current_device(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> AuthenticatedDevice:
    token = request.headers.get("X-EA-Device-Token", "")
    timestamp = request.headers.get("X-EA-Timestamp", "")
    nonce = request.headers.get("X-EA-Nonce", "")
    signature = request.headers.get("X-EA-Signature", "")
    if not token or not timestamp.isdigit() or not NONCE_PATTERN.fullmatch(nonce):
        raise APIError("invalid_device_auth", "Signed device headers are required", status.HTTP_401_UNAUTHORIZED)

    request_time = int(timestamp)
    if abs(int(time.time()) - request_time) > settings.request_max_age_seconds:
        raise APIError("stale_request", "Signed request timestamp is outside the allowed window", status.HTTP_401_UNAUTHORIZED)

    device = await session.scalar(
        select(Device).where(Device.token_hash == sha256_hex(token), Device.status == "ACTIVE")
    )
    if device is None:
        raise APIError("invalid_device_auth", "Device token is invalid or revoked", status.HTTP_401_UNAUTHORIZED)

    body = await request.body()
    expected = sign_ea_request(token, request.method, request.url.path, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature.lower()):
        raise APIError("invalid_signature", "Device request signature is invalid", status.HTTP_401_UNAUTHORIZED)

    try:
        accepted = await redis.set(
            f"ea:nonce:{device.id}:{nonce}", "1", ex=settings.nonce_ttl_seconds, nx=True
        )
    except Exception as exc:
        raise APIError(
            "replay_guard_unavailable",
            "Device request could not be safely verified",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if not accepted:
        raise APIError("replayed_request", "Signed request nonce has already been used", status.HTTP_401_UNAUTHORIZED)

    await enforce_rate_limit(redis, f"rate:device:{device.id}", settings.ea_rate_limit_per_minute)
    request.state.device_id = device.id
    return AuthenticatedDevice(device=device)