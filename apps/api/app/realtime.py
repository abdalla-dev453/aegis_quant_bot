from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from redis.asyncio import Redis


async def publish_user_event(
    redis: Redis, user_id: UUID, event_type: str, payload: dict[str, str | int | bool | None]
) -> None:
    message = json.dumps(
        {"type": event_type, "payload": payload},
        default=lambda value: str(value) if isinstance(value, (UUID, Decimal)) else value,
        separators=(",", ":"),
    )
    await redis.publish(f"app:user:{user_id}:events", message)