"""
Alert & Notification Dispatcher for Telegram and Discord Webhooks.

Provides instant mobile and community notifications for trade executions,
risk events, and emergency kill-switch actions.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class NotificationService:
    """Async notification dispatcher formatting rich Markdown/Embed alerts."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout = timeout_seconds

    async def send_webhook(self, webhook_url: str | None, payload: dict[str, Any]) -> bool:
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(webhook_url, json=payload)
                return res.status_code in (200, 204)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(f"[NotificationService] Failed to dispatch webhook: {exc}")
            return False

    async def notify_trade_opened(
        self,
        webhook_url: str | None,
        *,
        ticket: str,
        symbol: str,
        side: str,
        volume: Decimal,
        price: Decimal,
        sl: Decimal | None = None,
        tp: Decimal | None = None,
    ) -> bool:
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        message = (
            f"{emoji} **TRADE EXECUTED**\n"
            f"• **Ticket:** `{ticket}`\n"
            f"• **Symbol:** `{symbol}`\n"
            f"• **Side:** `{side.upper()}`\n"
            f"• **Volume:** `{volume}` lots\n"
            f"• **Entry Price:** `{price}`\n"
            f"• **SL:** `{sl or 'None'}` | **TP:** `{tp or 'None'}`"
        )
        payload = {"content": message, "text": message}
        return await self.send_webhook(webhook_url, payload)

    async def notify_trade_closed(
        self,
        webhook_url: str | None,
        *,
        ticket: str,
        symbol: str,
        realized_pnl: Decimal,
        exit_price: Decimal | None = None,
    ) -> bool:
        emoji = "🎉" if realized_pnl > 0 else "🛑"
        message = (
            f"{emoji} **TRADE CLOSED**\n"
            f"• **Ticket:** `{ticket}`\n"
            f"• **Symbol:** `{symbol}`\n"
            f"• **Exit Price:** `{exit_price or 'Market'}`\n"
            f"• **Realized PnL:** `${realized_pnl:+.2f}`"
        )
        payload = {"content": message, "text": message}
        return await self.send_webhook(webhook_url, payload)

    async def notify_kill_switch(
        self,
        webhook_url: str | None,
        *,
        user_id: UUID,
        reason: str = "User manual trigger or risk limit breach",
    ) -> bool:
        message = (
            f"🚨 **EMERGENCY KILL SWITCH ACTIVATED**\n"
            f"• **User ID:** `{user_id}`\n"
            f"• **Reason:** {reason}\n"
            f"• **Action:** All automated trading halted and positions requested closed."
        )
        payload = {"content": message, "text": message}
        return await self.send_webhook(webhook_url, payload)


# Global singleton instance
notification_service = NotificationService()
