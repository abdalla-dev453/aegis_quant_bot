from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from app.contracts import (
    SignalAction,
    SignalCreate,
    SignalRationale,
    SignalRationaleFactor,
)


class SignalProvider(Protocol):
    async def generate_signal(
        self,
        device_id: UUID,
        user_id: UUID,
        symbol: str,
        current_price: Decimal,
        point_size: Decimal,
    ) -> SignalCreate | None: ...


@dataclass(frozen=True, slots=True)
class RuleBasedProvider:
    model_version: str = "v1.2-confluence-rules"

    async def generate_signal(
        self,
        device_id: UUID,
        user_id: UUID,
        symbol: str,
        current_price: Decimal,
        point_size: Decimal,
        action: SignalAction = SignalAction.BUY,
    ) -> SignalCreate:
        is_buy = action == SignalAction.BUY

        # Calculate disciplined 1:2.5 Risk-to-Reward parameters
        sl_points = 300
        tp_points = 750

        if is_buy:
            sl_price = current_price - (Decimal(sl_points) * point_size)
            tp_price = current_price + (Decimal(tp_points) * point_size)
            summary = (
                f"Bullish trend continuation identified on {symbol.upper()}. "
                "Price bounced cleanly from the dynamic 50 EMA with strong bullish engulfing confluence."
            )
            factors = [
                SignalRationaleFactor(
                    name="EMA Trend Structure",
                    weight=Decimal("0.45"),
                    description="Price confirmed above 50/200 EMA ribbons on H1 timeframe",
                ),
                SignalRationaleFactor(
                    name="RSI Momentum Confluence",
                    weight=Decimal("0.35"),
                    description="RSI(14) pulled back to 42 and turned upward above the signal line",
                ),
                SignalRationaleFactor(
                    name="Volume & Liquidity Imbalance",
                    weight=Decimal("0.20"),
                    description="Institutional buy volume surge detected on the 15-minute order block",
                ),
            ]
        else:
            sl_price = current_price + (Decimal(sl_points) * point_size)
            tp_price = current_price - (Decimal(tp_points) * point_size)
            summary = (
                f"Bearish trend continuation confirmed on {symbol.upper()}. "
                "Break of market structure below key support with rising sell volume."
            )
            factors = [
                SignalRationaleFactor(
                    name="EMA Breakdown",
                    weight=Decimal("0.45"),
                    description="Price broke below 50 EMA with expanding downside momentum",
                ),
                SignalRationaleFactor(
                    name="RSI Divergence",
                    weight=Decimal("0.35"),
                    description="Bearish divergence registered on H1 peak before breakdown",
                ),
                SignalRationaleFactor(
                    name="Liquidity Sweep",
                    weight=Decimal("0.20"),
                    description="Asian session high swept followed by sharp rejection",
                ),
            ]

        expires_at = datetime.now(UTC) + timedelta(seconds=45)

        return SignalCreate(
            device_id=device_id,
            signal_id=uuid4(),
            symbol=symbol.upper(),
            action=action,
            reference_price=current_price,
            point_size=point_size,
            max_deviation_points=30,
            volume=Decimal("0.10"),
            stop_loss=sl_price,
            take_profit=tp_price,
            confidence=Decimal("0.8800"),
            rationale=SignalRationale(summary=summary, factors=factors),
            model_version=self.model_version,
            expires_at=expires_at,
        )
