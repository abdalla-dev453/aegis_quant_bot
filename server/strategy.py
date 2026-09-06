"""
strategy.py
-----------
Pure decision-making logic: no MT5 connection calls, no order placement.
Everything here takes DataFrames / primitives in and returns primitives
out, which makes it unit-testable without a live terminal.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.request
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import pandas_ta as ta

from config import INDICATORS, NEWS_CONFIG, STRATEGY

logger = logging.getLogger("trading_bot.strategy")


class Trend(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NONE = "none"


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds EMA fast/slow, RSI, and ATR columns to a copy of `df`.
    Expects columns: open, high, low, close.

    Returns an empty DataFrame (never raises) when the input is unusable
    (wrong columns, too few rows to warm up indicators, or all-NaN).
    """
    required = {"open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        logger.warning("compute_indicators: missing/invalid input columns %s", list(required))
        return pd.DataFrame()

    min_rows = INDICATORS.ema_slow + INDICATORS.rsi_period
    if len(df) < min_rows:
        logger.warning("compute_indicators: only %d rows, need >= %d to warm up", len(df), min_rows)
        return pd.DataFrame()

    out = df.copy()
    # Coerce to numeric and drop NaN rows so indicators never see dirty arrays
    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"])
    if out.empty:
        return pd.DataFrame()

    out[f"ema_{INDICATORS.ema_fast}"] = ta.ema(out["close"], length=INDICATORS.ema_fast)
    out[f"ema_{INDICATORS.ema_slow}"] = ta.ema(out["close"], length=INDICATORS.ema_slow)
    out["rsi"] = ta.rsi(out["close"], length=INDICATORS.rsi_period)
    out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=INDICATORS.atr_period)
    out.dropna(inplace=True)
    return out


def get_trend(df_with_indicators: pd.DataFrame) -> Trend:
    """
    EMA-crossover trend read on the last CLOSED candle of the given
    timeframe's DataFrame (H1 for trigger, H4 for bias).
    """
    if df_with_indicators.empty:
        return Trend.NEUTRAL

    last = df_with_indicators.iloc[-1]
    fast = last[f"ema_{INDICATORS.ema_fast}"]
    slow = last[f"ema_{INDICATORS.ema_slow}"]

    # NaN guard: an unwarmed indicator value must never trigger a trend call
    if pd.isna(fast) or pd.isna(slow):
        return Trend.NEUTRAL

    if fast > slow:
        return Trend.BULLISH
    if fast < slow:
        return Trend.BEARISH
    return Trend.NEUTRAL


def get_multi_timeframe_trend(df_h1: pd.DataFrame, df_h4: pd.DataFrame) -> Trend:
    """
    H4 sets the directional bias; H1 must agree for a trend to be confirmed.
    This is the core "multi-timeframe" requirement — a lone H1 crossover
    against the H4 bias is treated as noise (NEUTRAL), not a signal.
    """
    bias = get_trend(df_h4)
    trigger = get_trend(df_h1)

    if bias == Trend.NEUTRAL or trigger == Trend.NEUTRAL:
        return Trend.NEUTRAL
    if bias == trigger:
        return bias
    return Trend.NEUTRAL


def rsi_filter_ok(df_with_indicators: pd.DataFrame, direction: Trend) -> bool:
    """
    Uses a stronger confirmation gate than a flat overbought/oversold threshold.
    For bullish entries we require RSI to be above neutral, rising, and below
    the overbought ceiling. For bearish entries we require RSI to be below
    neutral, falling, and above the oversold floor.
    """
    if df_with_indicators.empty:
        return False

    rsi_series = pd.to_numeric(df_with_indicators["rsi"], errors="coerce").dropna()
    if rsi_series.empty or len(rsi_series) < 2:
        return False

    current = float(rsi_series.iloc[-1])
    previous = float(rsi_series.iloc[-2])

    if pd.isna(current) or pd.isna(previous):
        return False

    if direction == Trend.BULLISH:
        return current >= 52.0 and current > previous and current < INDICATORS.rsi_overbought
    if direction == Trend.BEARISH:
        return current <= 48.0 and current < previous and current > INDICATORS.rsi_oversold
    return False


def has_multi_timeframe_ema_rsi_confirmation(
    df_h1: pd.DataFrame, df_h4: pd.DataFrame, direction: Trend
) -> bool:
    """
    Requires both timeframes to agree on direction and for the trigger
    timeframe RSI to be in favorable momentum territory, not merely a stale
    crossover. This is the true multi-timeframe confirmation gate.
    """
    if df_h1.empty or df_h4.empty:
        return False

    h1_last = df_h1.iloc[-1]
    h4_last = df_h4.iloc[-1]

    def _coerce_float(value: object | None) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric

    fast_h1 = _coerce_float(h1_last.get(f"ema_{INDICATORS.ema_fast}"))
    slow_h1 = _coerce_float(h1_last.get(f"ema_{INDICATORS.ema_slow}"))
    fast_h4 = _coerce_float(h4_last.get(f"ema_{INDICATORS.ema_fast}"))
    slow_h4 = _coerce_float(h4_last.get(f"ema_{INDICATORS.ema_slow}"))
    rsi = _coerce_float(h1_last.get("rsi"))

    if fast_h1 is None or slow_h1 is None or fast_h4 is None or slow_h4 is None or rsi is None:
        return False

    assert fast_h1 is not None
    assert slow_h1 is not None
    assert fast_h4 is not None
    assert slow_h4 is not None
    assert rsi is not None

    if direction == Trend.BULLISH:
        return bool(fast_h4 > slow_h4 and fast_h1 > slow_h1 and rsi >= 52.0)
    if direction == Trend.BEARISH:
        return bool(fast_h4 < slow_h4 and fast_h1 < slow_h1 and rsi <= 48.0)
    return False


# ---------------------------------------------------------------------------
# Fundamental / sentiment engine (PLACEHOLDER)
# ---------------------------------------------------------------------------
@dataclass
class SentimentReading:
    score: float  # -1.0 (strongly bearish) .. +1.0 (strongly bullish)
    headline_count: int
    next_high_impact_event: str | None
    minutes_to_next_event: (
        float | None
    )  # negative if the event already started/passed within window


def _neutral_reading() -> SentimentReading:
    """Neutral fallback used whenever the sentiment feed is unavailable."""
    return SentimentReading(
        score=0.0, headline_count=0, next_high_impact_event=None, minutes_to_next_event=None
    )


def analyze_market_sentiment(symbol: str) -> SentimentReading:
    """
    Fetches sentiment + next high-impact event from the configured news API
    (NEWS_CONFIG.base_url / NEWS_CONFIG.api_key).

    Fail-safe by design: any network / payload / auth problem returns a
    NEUTRAL reading. The bot must never crash or trade on garbage because a
    third-party feed hiccupped. NOTE: with no real API key configured the
    request will simply fail and the neutral fallback is used.
    """
    if not NEWS_CONFIG.api_key or not NEWS_CONFIG.base_url:
        logger.warning("News API not configured (%s) — using neutral sentiment.", symbol)
        return _neutral_reading()

    url = f"{NEWS_CONFIG.base_url.rstrip('/')}/sentiment"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {NEWS_CONFIG.api_key}",
            "Accept": "application/json",
            "X-Symbol": symbol,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=NEWS_CONFIG.api_timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Sentiment fetch failed for %s (%s) — using neutral sentiment.", symbol, e)
        return _neutral_reading()

    try:
        headlines = payload.get("headlines", [])
        scores = [float(h["sentiment"]) for h in headlines if math.isfinite(float(h["sentiment"]))]
        aggregate = round(sum(scores) / len(scores), 3) if scores else 0.0
        aggregate = max(-1.0, min(1.0, aggregate))

        event = payload.get("next_event") or {}
        event_name = event.get("name")
        minutes = event.get("minutes_away")
        minutes_f = float(minutes) if minutes is not None else None

        return SentimentReading(
            score=aggregate,
            headline_count=len(headlines),
            next_high_impact_event=event_name,
            minutes_to_next_event=minutes_f,
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Malformed sentiment payload for %s (%s) — using neutral.", symbol, e)
        return _neutral_reading()


def is_news_blackout(sentiment: SentimentReading) -> bool:
    """
    True if we're inside the blackout window around a high-impact release
    (30 min before / 30 min after by default). `minutes_to_next_event` is
    positive if the event is upcoming, negative if it already occurred.
    """
    if sentiment.next_high_impact_event not in NEWS_CONFIG.high_impact_events:
        return False
    if sentiment.minutes_to_next_event is None:
        return False

    m = sentiment.minutes_to_next_event
    if 0 <= m <= NEWS_CONFIG.blackout_minutes_before:
        return True
    if -NEWS_CONFIG.blackout_minutes_after <= m < 0:
        return True
    return False


# ---------------------------------------------------------------------------
# Confluence — technical + fundamental fusion
# ---------------------------------------------------------------------------
@dataclass
class TradeSignal:
    direction: TradeDirection
    reason: str
    technical_trend: Trend
    sentiment_score: float
    atr: float


def generate_signal(
    symbol: str,
    df_h1_ind: pd.DataFrame,
    df_h4_ind: pd.DataFrame,
) -> TradeSignal:
    """
    A signal is valid ONLY when:
      1. H1 and H4 EMA trend agree (multi-timeframe confluence), AND
      2. RSI isn't already overbought/oversold in that direction, AND
      3. Sentiment score crosses the configured threshold in the SAME
         direction as the technical trend, AND
      4. We are not inside a high-impact news blackout window.
    """
    if df_h1_ind.empty or df_h4_ind.empty:
        return TradeSignal(
            TradeDirection.NONE, "Insufficient warmed-up data", Trend.NEUTRAL, 0.0, 0.0
        )

    atr = float(df_h1_ind.iloc[-1]["atr"])
    if not math.isfinite(atr) or atr <= 0.0:
        # A zero/NaN ATR would produce degenerate SL/TP and unsafe sizing — block.
        return TradeSignal(
            TradeDirection.NONE, "ATR unavailable/degenerate", Trend.NEUTRAL, 0.0, 0.0
        )

    trend = get_multi_timeframe_trend(df_h1_ind, df_h4_ind)
    sentiment = analyze_market_sentiment(symbol)

    if is_news_blackout(sentiment):
        return TradeSignal(
            TradeDirection.NONE,
            f"News blackout active ({sentiment.next_high_impact_event}, "
            f"{sentiment.minutes_to_next_event:.0f} min)",
            trend,
            sentiment.score,
            atr,
        )

    if trend == Trend.NEUTRAL:
        return TradeSignal(
            TradeDirection.NONE, "No H1/H4 trend agreement", trend, sentiment.score, atr
        )

    if not has_multi_timeframe_ema_rsi_confirmation(df_h1_ind, df_h4_ind, trend):
        return TradeSignal(
            TradeDirection.NONE,
            "H1/H4 EMA + RSI confirmation not satisfied",
            trend,
            sentiment.score,
            atr,
        )

    if not rsi_filter_ok(df_h1_ind, trend):
        return TradeSignal(
            TradeDirection.NONE, "RSI filter blocked entry", trend, sentiment.score, atr
        )

    if trend == Trend.BULLISH and sentiment.score > STRATEGY.sentiment_bullish_threshold:
        return TradeSignal(
            TradeDirection.BUY,
            "Technical bullish + sentiment confirms",
            trend,
            sentiment.score,
            atr,
        )

    if trend == Trend.BEARISH and sentiment.score < STRATEGY.sentiment_bearish_threshold:
        return TradeSignal(
            TradeDirection.SELL,
            "Technical bearish + sentiment confirms",
            trend,
            sentiment.score,
            atr,
        )

    return TradeSignal(
        TradeDirection.NONE,
        f"Technical trend ({trend.value}) not confirmed by sentiment ({sentiment.score:+.2f})",
        trend,
        sentiment.score,
        atr,
    )
