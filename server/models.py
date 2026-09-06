"""
models.py
---------
Single source of truth for the API data contract between the Python bot and
the React dashboard (client/src/lib/botFeed.js mirrors these shapes exactly).
If you change a field here, change it there too — nothing else needs editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AccountState:
    netEquity: float
    balance: float
    todaysPnl: float
    freeMargin: float
    marginLevel: float


@dataclass
class RiskState:
    drawdownPct: float
    maxDrawdownCeilingPct: float
    marginUtilizedPct: float
    openPositions: int
    dailyVaR: float
    riskPerTradePct: float | None = None  # from config.RISK.risk_per_trade_pct


@dataclass
class PricePoint:
    time: str  # ISO datetime (UTC)
    price: float
    ema50: float
    ema200: float


@dataclass
class PriceSeries:
    """Wrapper so the /api/price-series endpoint can carry its symbol."""

    symbol: str
    points: list[PricePoint]


@dataclass
class PerformanceState:
    winRatePct: float
    profitFactor: float
    totalTrades: int
    avgWin: float
    avgLoss: float


@dataclass
class ConfluenceState:
    composite: float  # -1.0 .. +1.0
    label: str  # e.g. "STRONG BULL"
    technical: float
    sentiment: float
    momentum: float


@dataclass
class CalendarEvent:
    name: str
    currency: str
    impact: str  # "HIGH" | "MEDIUM" | "LOW"
    timeUtc: str
    minutesAway: float


@dataclass
class CalendarState:
    autoHaltActive: bool
    autoHaltEtaSeconds: int
    nextEvent: CalendarEvent | None


@dataclass
class Position:
    ticket: str
    symbol: str
    type: str  # "BUY" | "SELL"
    lot: float
    entry: float
    sl: float
    tp: float
    trailing: bool
    current: float
    pnl: float


@dataclass
class EquityPoint:
    date: str  # ISO date, e.g. "2025-01-15"
    equity: float




@dataclass
class LogEntry:
    id: str
    time: str  # "HH:MM:SS"
    level: str  # "INFO" | "WARN" | "ERROR"
    message: str


def to_dict(obj: Any) -> Any:
    """Serialize a dataclass (or list of dataclasses) to plain JSON-safe dicts."""
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj
