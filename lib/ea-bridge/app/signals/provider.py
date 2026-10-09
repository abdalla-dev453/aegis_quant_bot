"""Signal-provider boundary.

The former implementation emitted fixed BUY/SELL orders and described
indicators it never calculated. Keep the provider fail-closed until a real,
timestamped market-data strategy is wired into this interface.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.contracts import SignalCreate


class SignalGenerationUnavailable(RuntimeError):
    """Raised when no qualified signal engine is configured."""


class SignalProvider(Protocol):
    async def generate_signal(
        self,
        device_id: UUID,
        user_id: UUID,
        symbol: str,
        current_price: Decimal,
        point_size: Decimal,
    ) -> SignalCreate | None: ...


class RuleBasedProvider:
    """Fail-closed placeholder; never manufactures an executable signal."""

    model_version = "unqualified-no-signal-engine"

    async def generate_signal(
        self,
        device_id: UUID,
        user_id: UUID,
        symbol: str,
        current_price: Decimal,
        point_size: Decimal,
    ) -> SignalCreate | None:
        raise SignalGenerationUnavailable(
            "Signal dispatch is disabled: no qualified market-data strategy is configured."
        )
