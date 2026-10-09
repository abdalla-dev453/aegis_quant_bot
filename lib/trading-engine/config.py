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

import math
import os
from dataclasses import dataclass
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


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


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
    expected_login: int | None = _env_int("MT5_EXPECTED_LOGIN", 0) or None
    expected_server: str | None = os.getenv("MT5_EXPECTED_SERVER") or None
    expected_trade_mode: str = os.getenv("MT5_EXPECTED_TRADE_MODE", "demo").lower()
    expected_margin_mode: str = os.getenv("MT5_EXPECTED_MARGIN_MODE", "hedging").lower()

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
        if self.expected_login is None or not self.expected_server:
            raise ValueError("Live trading requires MT5_EXPECTED_LOGIN and MT5_EXPECTED_SERVER")
        if self.expected_trade_mode not in {"demo", "real"}:
            raise ValueError("MT5_EXPECTED_TRADE_MODE must be 'demo' or 'real'")
        if self.expected_margin_mode not in {"hedging", "netting"}:
            raise ValueError("MT5_EXPECTED_MARGIN_MODE must be 'hedging' or 'netting'")


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
    min_confidence: float = _env_float("AI_MIN_CONFIDENCE", 0.70)

    def validate(self) -> None:
        if self.provider != "openai":
            raise ValueError("Only AI_PROVIDER=openai is supported by this deployment.")
        if not self.api_key:
            raise ValueError("Missing OPENAI_API_KEY. Set it in server/.env or the environment.")
        if self.timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be greater than zero.")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("AI_MIN_CONFIDENCE must be between 0 and 1")


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
        from urllib.parse import urlparse
        if not self.api_host:
            raise ValueError("API_HOST must not be empty")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("API_PORT must be between 1 and 65535")
        if self.max_candle_age_seconds <= 0:
            raise ValueError("MAX_CANDLE_AGE_SECONDS must be greater than zero")
        if os.getenv("TRADING_MODE", "paper").lower() == "live" and not os.getenv("API_TOKEN"):
            raise ValueError("API_TOKEN is required for live trading")
        if not self.cors_origins or any(origin == "*" or urlparse(origin).scheme not in {"http", "https"} or not urlparse(origin).netloc for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain absolute non-wildcard URLs")


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
    risk_per_trade_pct: float = _env_float("RISK_PER_TRADE_PCT", 1.5)  # % of equity risked per trade
    max_daily_loss_pct: float = _env_float("MAX_DAILY_LOSS_PCT", 4.0)  # halt new entries for the rest of the day past this drawdown
    max_weekly_loss_pct: float = _env_float("MAX_WEEKLY_LOSS_PCT", 6.0)
    # This is intentionally independent of the daily-loss guard.  It is a
    # high-water-mark circuit breaker and remains latched until manually reset.
    max_drawdown_from_peak_pct: float = _env_float("MAX_DRAWDOWN_FROM_PEAK_PCT", 8.0)
    max_trades_per_day: int = _env_int("MAX_TRADES_PER_DAY", 6)
    correlation_threshold: float = _env_float("CORRELATION_THRESHOLD", 0.70)
    atr_sl_multiplier: float = _env_float("ATR_SL_MULTIPLIER", 1.5)  # SL = entry -/+ (ATR * multiplier)
    atr_tp_multiplier: float = _env_float("ATR_TP_MULTIPLIER", 3.0)  # TP = entry -/+ (ATR * multiplier) -> 2:1 default
    trailing_trigger_rr: float = _env_float("TRAILING_TRIGGER_RR", 1.0)  # start trailing once trade hits 1:1 RR
    trailing_atr_multiplier: float = _env_float("TRAILING_ATR_MULTIPLIER", 1.0)  # trailing distance once triggered
    max_concurrent_positions: int = _env_int("MAX_CONCURRENT_POSITIONS", 3)
    max_aggregate_risk_pct: float = _env_float("MAX_AGGREGATE_RISK_PCT", 3.0)
    max_spread_points: float = _env_float("MAX_SPREAD_POINTS", 50.0)
    max_stop_atr_multiplier: float = _env_float("MAX_STOP_ATR_MULTIPLIER", 3.0)
    min_reward_risk_ratio: float = _env_float("MIN_REWARD_RISK_RATIO", 1.0)
    max_reward_risk_ratio: float = _env_float("MAX_REWARD_RISK_RATIO", 5.0)
    magic_number: int = 990011
    deviation_points: int = _env_int("DEVIATION_POINTS", 20)  # max slippage tolerance

    def validate(self) -> None:
        float_settings = {
            "RISK_PER_TRADE_PCT": self.risk_per_trade_pct,
            "MAX_DAILY_LOSS_PCT": self.max_daily_loss_pct,
            "MAX_WEEKLY_LOSS_PCT": self.max_weekly_loss_pct,
            "MAX_DRAWDOWN_FROM_PEAK_PCT": self.max_drawdown_from_peak_pct,
            "CORRELATION_THRESHOLD": self.correlation_threshold,
            "ATR_SL_MULTIPLIER": self.atr_sl_multiplier,
            "ATR_TP_MULTIPLIER": self.atr_tp_multiplier,
            "TRAILING_TRIGGER_RR": self.trailing_trigger_rr,
            "TRAILING_ATR_MULTIPLIER": self.trailing_atr_multiplier,
            "MAX_AGGREGATE_RISK_PCT": self.max_aggregate_risk_pct,
            "MAX_SPREAD_POINTS": self.max_spread_points,
            "MAX_STOP_ATR_MULTIPLIER": self.max_stop_atr_multiplier,
            "MIN_REWARD_RISK_RATIO": self.min_reward_risk_ratio,
            "MAX_REWARD_RISK_RATIO": self.max_reward_risk_ratio,
        }
        for name, value in float_settings.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        percentages = {
            "RISK_PER_TRADE_PCT": self.risk_per_trade_pct,
            "MAX_DAILY_LOSS_PCT": self.max_daily_loss_pct,
            "MAX_WEEKLY_LOSS_PCT": self.max_weekly_loss_pct,
            "MAX_DRAWDOWN_FROM_PEAK_PCT": self.max_drawdown_from_peak_pct,
            "MAX_AGGREGATE_RISK_PCT": self.max_aggregate_risk_pct,
        }
        for name, value in percentages.items():
            if not 0.0 < value <= 100.0:
                raise ValueError(f"{name} must be greater than 0 and at most 100")
        if self.max_trades_per_day < 1:
            raise ValueError("MAX_TRADES_PER_DAY must be at least 1")
        if self.max_concurrent_positions < 1:
            raise ValueError("MAX_CONCURRENT_POSITIONS must be at least 1")
        if self.max_spread_points <= 0:
            raise ValueError("MAX_SPREAD_POINTS must be greater than zero")
        if self.max_aggregate_risk_pct < self.risk_per_trade_pct:
            raise ValueError("MAX_AGGREGATE_RISK_PCT must be at least RISK_PER_TRADE_PCT")
        if self.max_stop_atr_multiplier <= 0:
            raise ValueError("MAX_STOP_ATR_MULTIPLIER must be greater than zero")
        if self.min_reward_risk_ratio <= 0 or self.max_reward_risk_ratio < self.min_reward_risk_ratio:
            raise ValueError("Reward/risk ratio bounds are invalid")
        if not 0.0 <= self.correlation_threshold <= 1.0:
            raise ValueError("CORRELATION_THRESHOLD must be between 0 and 1")
        for name, value in (
            ("ATR_SL_MULTIPLIER", self.atr_sl_multiplier),
            ("ATR_TP_MULTIPLIER", self.atr_tp_multiplier),
        ):
            if value <= 0.0:
                raise ValueError(f"{name} must be greater than 0")
        if self.trailing_trigger_rr < 0.0 or self.trailing_atr_multiplier < 0.0:
            raise ValueError("Trailing-stop multipliers must not be negative")
        if self.deviation_points < 0:
            raise ValueError("DEVIATION_POINTS must not be negative")


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
    ("EURUSD", "XAUUSD"): -0.3,
    ("GBPUSD", "XAUUSD"): -0.2,
}


# ----------------------------------------------------------
# Strategy / confluence thresholds
# ------------------------------------------------------------
@dataclass(frozen=True)
class StrategyConfig:
    # Sentiment is optional by design; when disabled, only technical
    # confluence authorizes direction. News availability remains a separate gate.
    require_sentiment_feed: bool = os.getenv("REQUIRE_SENTIMENT_FEED", "false").lower() == "true"
    require_news_feed: bool = os.getenv("REQUIRE_NEWS_FEED", "true").lower() == "true"
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
