"""
config.py
---------
Central configuration for the trading bot. Nothing in here talks to MT5 or
the network — it's pure settings, so every other module can import it safely
without side effects.

SECURITY NOTE: Do not commit real credentials to version control. In
production, load MT5_LOGIN / MT5_PASSWORD / MT5_SERVER and any news-API
keys from environment variables (os.environ) or a secrets manager instead
of hardcoding them here. The placeholders below are for local dev only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final


# -------------------------------------------------------------
# MT5 terminal / account credentials
# -------------------------------------------------------------
@dataclass(frozen=True)
class MT5Credentials:
    login: int = int(os.getenv("MT5_LOGIN") or "0")
    password: str = os.getenv("MT5_PASSWORD") or ""
    server: str = os.getenv("MT5_SERVER") or ""

    # Full path to terminal64.exe. Leave None to let MT5 auto-detect an
    # already-running terminal instance instead of launching a new one.
    terminal_path: str | None = os.getenv("MT5_TERMINAL_PATH") or None
    # Milliseconds to wait for the terminal to respond before giving up.
    timeout_ms: int = 60_000

    def is_configured(self) -> bool:
        return bool(self.login and self.password and self.server)

    def validate_live_trade_config(self) -> None:
        missing = []
        if not self.login:
            missing.append("MT5_LOGIN")
        if not self.password:
            missing.append("MT5_PASSWORD")
        if not self.server:
            missing.append("MT5_SERVER")
        if missing:
            raise ValueError("Missing MT5 live-trading configuration: " + ", ".join(missing))


# -------------------------------------------------------
# News / sentiment provider (placeholder — swap in a real API key + client)
# -------------------------------------------------------------
@dataclass(frozen=True)
class NewsAPIConfig:
    api_key: str = os.getenv("NEWS_API_KEY", "")
    base_url: str = os.getenv("NEWS_API_BASE_URL", "https://api.example-economic-calendar.com/v1")
    api_timeout_seconds: int = 10

    # How long before/after a high-impact release the bot refuses new trades
    blackout_minutes_before: int = 30
    blackout_minutes_after: int = 30

    # Events considered "high impact" for blackout purposes
    high_impact_events: tuple[str, ...] = (
        "CPI",
        "Interest Rate Decision",
        "Non-Farm Payrolls",
        "FOMC Statement",
        "GDP",
    )


# -----------------------------------------------
# Symbols & timeframes
# ---------------------------------
@dataclass(frozen=True)
class SymbolConfig:
    name: str
    # Min distance ( in points ) the broker enforces btwn price and SL/TP. Fetched at runtime from symbol_info when possible; this is a conservative fallback
    fallback_stops_level_points: int = 100
    pip_value_per_lot: float = 10.0


TRADING_SYMBOLS: Final[list[SymbolConfig]] = [
    SymbolConfig(name="EURUSD"),
    SymbolConfig(name="GBPUSD"),
    SymbolConfig(name="XAUUSD", fallback_stops_level_points=200, pip_value_per_lot=1.0),
]


# MT5 timeframe constants are ints from the MetaTrader5 module; we reference
# them by name here and resolve the actual mt5.TIMEFRAME_* value inside
# data_provider.py so config.py has zero dependency on the MT5 SDK.
TIMEFRAME_TRIGGER: Final[str] = "H1"  # entry trigger timeframe
TIMEFRAME_BIAS: Final[str] = "H4"  # higher-timeframe directional bias
CANDLES_TO_FETCH: Final[int] = 400  # enough history for EMA200 to warm up


# -----------------------------------------------------------
# Indicator parameters
# -------------------------------------------------------
@dataclass(frozen=True)
class IndicatorConfig:
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14


# --------------------------------------------------------
# Risk management
# ----------------------------------------------------------
@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float = 1.5  # % of equity risked per trade
    atr_sl_multiplier: float = 1.5  # SL = entry -/+ (ATR * multiplier)
    atr_tp_multiplier: float = 3.0  # TP = entry -/+ (ATR * multiplier) -> 2:1 default
    trailing_trigger_rr: float = 1.0  # start trailing once trade hits 1:1 RR
    trailing_atr_multiplier: float = 1.0  # trailing distance once triggered
    max_concurrent_positions: int = 3
    magic_number: int = 990011
    deviation_points: int = 20  # max slippage tolerance


# ----------------------------------------------------------
# Strategy / confluence thresholds
# ------------------------------------------------------------
@dataclass(frozen=True)
class StrategyConfig:
    sentiment_bullish_threshold: float = 0.5
    sentiment_bearish_threshold: float = -0.5
    loop_poll_seconds: int = 15  # how often the main loop checks for a new closed candle


# ---------------------------------------------------------------
# Logging
# ------------------------------------------------------------
@dataclass(frozen=True)
class LoggingConfig:
    log_file: str = "trading_bot.log"
    level: str = os.getenv("LOG_LEVEL", "INFO")


# Single point of truth every other module imports.
CREDENTIALS = MT5Credentials()
NEWS_CONFIG = NewsAPIConfig()
INDICATORS = IndicatorConfig()
RISK = RiskConfig()
STRATEGY = StrategyConfig()
LOGGING = LoggingConfig()

# Max retries / backoff ceiling for connection-level operations.
MAX_RECONNECT_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
