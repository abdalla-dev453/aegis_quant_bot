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
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Load only this service's local file, never overwrite explicitly supplied
# deployment secrets, and keep .env out of version control.
load_dotenv(Path(__file__).with_name(".env"), override=False)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


# -------------------------------------------------------------
# MT5 terminal / account credentials
# -------------------------------------------------------------
@dataclass(frozen=True)
class MT5Credentials:
    login: int | None = None
    password: str | None = None
    server: str | None = None

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
    news_api_url: str = os.getenv("NEWS_API_URL", "https://newsapi.org/v2/everything")
    api_timeout_seconds: int = 10
    cache_seconds: int = 60
    yahoo_rss_url: str = os.getenv(
        "YAHOO_FINANCE_RSS_URL",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD%3DX%2CGBPUSD%3DX%2CGC%3DF&region=US&lang=en-US",
    )

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


@dataclass(frozen=True)
class AIConfig:
    provider: str = os.getenv("AI_PROVIDER", "openai").lower()
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    timeout_seconds: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))

    def validate(self) -> None:
        if self.provider != "openai":
            raise ValueError("Only AI_PROVIDER=openai is supported by this deployment.")
        if not self.api_key:
            raise ValueError("Missing OPENAI_API_KEY. Set it in server/.env or the environment.")
        if self.timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be greater than zero.")


@dataclass(frozen=True)
class DeploymentConfig:
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = _env_int("API_PORT", 8000)
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
    max_candle_age_seconds: int = _env_int("MAX_CANDLE_AGE_SECONDS", 7200)

    def validate(self) -> None:
        if not self.api_host:
            raise ValueError("API_HOST must not be empty")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("API_PORT must be between 1 and 65535")
        if self.max_candle_age_seconds <= 0:
            raise ValueError("MAX_CANDLE_AGE_SECONDS must be greater than zero")


# -----------------------------------------------
# Symbols & timeframes
# -----------------------------------------------
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
    max_daily_loss_pct: float = 4.0  # halt new entries for the rest of the day past this drawdown
    # This is intentionally independent of the daily-loss guard.  It is a
    # high-water-mark circuit breaker and remains latched until manually reset.
    max_drawdown_from_peak_pct: float = 8.0
    max_trades_per_day: int = 6
    correlation_threshold: float = 0.70
    atr_sl_multiplier: float = 1.5  # SL = entry -/+ (ATR * multiplier)
    atr_tp_multiplier: float = 3.0  # TP = entry -/+ (ATR * multiplier) -> 2:1 default
    trailing_trigger_rr: float = 1.0  # start trailing once trade hits 1:1 RR
    trailing_atr_multiplier: float = 1.0  # trailing distance once triggered
    max_concurrent_positions: int = 3
    magic_number: int = 990011
    deviation_points: int = 20  # max slippage tolerance


@dataclass(frozen=True)
class ExecutionConfig:
    """Live order submission is opt-in; paper is the safe deployment default."""

    mode: str = os.getenv("TRADING_MODE", "paper").lower()

    def validate(self) -> None:
        if self.mode not in {"paper", "live"}:
            raise ValueError("TRADING_MODE must be either 'paper' or 'live'.")

    @property
    def live_orders_enabled(self) -> bool:
        return self.mode == "live"


# Correlations used as a conservative pre-trade exposure guard.  Keep this
# explicit (rather than pretending a short price history is a reliable
# estimate) and extend it when adding tradable symbols.
SYMBOL_CORRELATIONS: Final[dict[tuple[str, str], float]] = {
    ("EURUSD", "GBPUSD"): 0.85,
}


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
    log_file: str = os.getenv("LOG_FILE", "trading_bot.log")
    level: str = os.getenv("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------
# Advanced Analysis Configuration
# ---------------------------------------------------------------
@dataclass(frozen=True)
class AdvancedAnalysisConfig:
    # Trend analysis enhancements
    use_adx: bool = True
    adx_period: int = 14
    adx_trend_threshold: float = 25.0
    use_macd: bool = True
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    # Volume analysis
    use_volume_confirmation: bool = True
    volume_surge_threshold: float = 1.5
    volume_lookback_period: int = 20
    
    # Market regime detection
    enable_regime_detection: bool = True
    regime_volatility_threshold: float = 0.02
    regime_adx_threshold: float = 25.0
    
    # Support/Resistance levels
    enable_level_detection: bool = True
    pivot_lookback_period: int = 50
    psychological_level_rounding: int = 100  # For round number detection


# ---------------------------------------------------------------
# Prediction & AI Configuration
# ---------------------------------------------------------------
@dataclass(frozen=True)
class PredictionConfig:
    # Price prediction
    enable_price_prediction: bool = False  # Opt-in feature
    prediction_lookahead_bars: int = 5
    prediction_confidence_threshold: float = 0.6
    
    # Pattern recognition
    enable_pattern_detection: bool = True
    pattern_confidence_threshold: float = 0.7
    pattern_lookback_period: int = 100
    
    # Volatility forecasting
    enable_volatility_forecasting: bool = True
    volatility_forecast_horizon: int = 10
    garch_model_enabled: bool = False  # Requires additional dependencies
    
    # Ensemble AI
    enable_ensemble_ai: bool = False  # Opt-in feature
    ai_weight_primary: float = 0.7
    ai_weight_secondary: float = 0.3


# ---------------------------------------------------------------
# Self-Healing & Automation Configuration
# ---------------------------------------------------------------
@dataclass(frozen=True)
class SelfHealingConfig:
    enable_self_healing: bool = True
    max_recovery_attempts: int = 3
    recovery_backoff_base: float = 5.0
    recovery_backoff_max: float = 60.0
    
    # Data quality monitoring
    enable_data_quality_checks: bool = True
    max_nan_ratio: float = 0.1
    min_data_points: int = 50
    
    # Connection health monitoring
    connection_timeout_seconds: int = 30
    max_connection_failures: int = 5


# ---------------------------------------------------------------
# Adaptive Optimization Configuration
# ---------------------------------------------------------------
@dataclass(frozen=True)
class AdaptiveConfig:
    enable_adaptive_parameters: bool = True
    optimization_window_days: int = 7
    min_trades_for_optimization: int = 10
    
    # Performance thresholds for parameter adjustment
    win_rate_lower_threshold: float = 0.4
    win_rate_upper_threshold: float = 0.6
    profit_factor_threshold: float = 1.5
    
    # Parameter adjustment ranges
    rsi_adjustment_range: float = 5.0
    sentiment_adjustment_range: float = 0.2
    risk_adjustment_range: float = 0.5


# ---------------------------------------------------------------
# Advanced Risk Management Configuration
# ---------------------------------------------------------------
@dataclass(frozen=True)
class AdvancedRiskConfig:
    # Portfolio-level controls
    enable_portfolio_risk: bool = True
    max_portfolio_exposure_pct: float = 10.0
    max_correlation_exposure_pct: float = 5.0
    max_currency_concentration_pct: float = 7.0
    
    # Dynamic volatility-based sizing
    enable_volatility_adjusted_sizing: bool = True
    volatility_lookback_period: int = 50
    high_volatility_multiplier: float = 0.5
    low_volatility_multiplier: float = 1.2
    volatility_ratio_high: float = 1.5
    volatility_ratio_low: float = 0.5


# Single point of truth every other module imports.
CREDENTIALS = MT5Credentials()
NEWS_CONFIG = NewsAPIConfig()
AI = AIConfig()
DEPLOYMENT = DeploymentConfig()
INDICATORS = IndicatorConfig()
RISK = RiskConfig()
EXECUTION = ExecutionConfig()
STRATEGY = StrategyConfig()
LOGGING = LoggingConfig()
ADVANCED_ANALYSIS = AdvancedAnalysisConfig()
PREDICTION = PredictionConfig()
SELF_HEALING = SelfHealingConfig()
ADAPTIVE = AdaptiveConfig()
ADVANCED_RISK = AdvancedRiskConfig()

# Max retries / backoff ceiling for connection-level operations.
MAX_RECONNECT_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
