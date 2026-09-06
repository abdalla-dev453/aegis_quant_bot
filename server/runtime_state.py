"""Thread-safe read-only snapshots shared by the trading loop and API."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

_lock = Lock()
_snapshot: dict[str, Any] = {
    "connected": False,
    "last_signal": {},
    "logs": [],
    "started_at": datetime.now(timezone.utc).isoformat(),
}


def update(**values: Any) -> None:
    with _lock:
        _snapshot.update(values)


def read() -> dict[str, Any]:
    with _lock:
        result = dict(_snapshot)
        result["logs"] = list(_snapshot.get("logs", []))
        return result


def add_log(level: str, message: str) -> None:
    with _lock:
        logs = _snapshot.setdefault("logs", [])
        logs.append(
            {
                "id": f"{datetime.now(timezone.utc).timestamp():.6f}",
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            }
        )
        del logs[:-200]
