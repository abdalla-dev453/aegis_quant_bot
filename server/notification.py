"""Trade notification system for critical events."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("trading_bot.notifications")


class NotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Notification:
    level: NotificationLevel
    title: str
    message: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class NotificationChannel(str, Enum):
    LOG = "log"


class NotificationManager:
    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = [NotificationChannel.LOG]
        self._lock = threading.Lock()
        self._history: list[Notification] = []
        self._max_history = 200

    def add_channel(self, channel: NotificationChannel) -> None:
        with self._lock:
            if channel not in self._channels:
                self._channels.append(channel)

    def notify(
        self,
        level: NotificationLevel,
        title: str,
        message: str,
        **metadata: Any,
    ) -> Notification:
        notification = Notification(
            level=level, title=title, message=message, metadata=metadata
        )
        with self._lock:
            self._history.append(notification)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        for channel in self._channels:
            if channel == NotificationChannel.LOG:
                self._log_notification(notification)

        return notification

    def _log_notification(self, notification: Notification) -> None:
        prefix = f"[{notification.level.value.upper()}]"
        logger.info(f"{prefix} {notification.title}: {notification.message}")

    def critical(
        self, title: str, message: str, **metadata: Any
    ) -> Notification:
        return self.notify(NotificationLevel.CRITICAL, title, message, **metadata)

    def warning(
        self, title: str, message: str, **metadata: Any
    ) -> Notification:
        return self.notify(NotificationLevel.WARNING, title, message, **metadata)

    def info(
        self, title: str, message: str, **metadata: Any
    ) -> Notification:
        return self.notify(NotificationLevel.INFO, title, message, **metadata)

    def get_history(
        self, level: NotificationLevel | None = None, limit: int = 50
    ) -> list[Notification]:
        with self._lock:
            if level is not None:
                filtered = [n for n in self._history if n.level == level]
            else:
                filtered = list(self._history)
            return filtered[-limit:]


notification_manager = NotificationManager()
