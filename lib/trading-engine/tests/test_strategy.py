"""Pure strategy gates: no MT5 terminal or network connection is required."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

import strategy
from strategy import SentimentReading, TradeDirection, Trend


def _frame(fast: float, slow: float, rsi_values: tuple[float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ema_50": [fast, fast],
            "ema_200": [slow, slow],
            "rsi": list(rsi_values),
            "atr": [0.001, 0.001],
        }
    )


def test_multi_timeframe_confirmation_requires_both_ema_trends_and_rsi() -> None:
    h1 = _frame(1.11, 1.10, (54.0, 56.0))
    h4 = _frame(1.12, 1.10, (50.0, 50.0))

    assert strategy.has_multi_timeframe_ema_rsi_confirmation(h1, h4, Trend.BULLISH)
    assert not strategy.has_multi_timeframe_ema_rsi_confirmation(h1, h4, Trend.BEARISH)


@pytest.mark.parametrize(
    ("minutes", "impact", "expected"),
    [(30, "HIGH", True), (-30, "HIGH", True), (31, "HIGH", False), (5, "LOW", False)],
)
def test_news_blackout_only_applies_inside_high_impact_window(
    minutes: float, impact: str, expected: bool
) -> None:
    reading = SentimentReading(0.0, 0, "CPI", minutes, next_event_impact=impact)
    assert strategy.is_news_blackout(reading) is expected


def test_technical_confluence_can_authorize_without_fake_sentiment(monkeypatch: pytest.MonkeyPatch) -> None:
    h1 = _frame(1.11, 1.10, (54.0, 56.0))
    h4 = _frame(1.12, 1.10, (50.0, 50.0))
    monkeypatch.setattr(
        strategy, "STRATEGY", replace(strategy.STRATEGY, require_sentiment_feed=False)
    )
    monkeypatch.setattr(
        strategy,
        "analyze_market_sentiment",
        lambda _symbol: SentimentReading(-0.8, 1, None, None),
    )

    signal = strategy.generate_signal("EURUSD", h1, h4)

    assert signal.direction == TradeDirection.BUY
    assert "informational only" in signal.reason


def test_technical_bearish_confluence_can_authorize_sell(monkeypatch: pytest.MonkeyPatch) -> None:
    h1 = _frame(1.09, 1.10, (44.0, 42.0))
    h4 = _frame(1.08, 1.10, (50.0, 50.0))
    monkeypatch.setattr(
        strategy, "STRATEGY", replace(strategy.STRATEGY, require_sentiment_feed=False)
    )
    monkeypatch.setattr(
        strategy,
        "analyze_market_sentiment",
        lambda _symbol: SentimentReading(0.9, 1, None, None),
    )

    signal = strategy.generate_signal("EURUSD", h1, h4)

    assert signal.direction == TradeDirection.SELL
    assert "informational only" in signal.reason


def test_strategy_uses_supplied_news_snapshot_without_second_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h1 = _frame(1.11, 1.10, (54.0, 56.0))
    h4 = _frame(1.12, 1.10, (50.0, 50.0))
    monkeypatch.setattr(
        strategy, "STRATEGY", replace(strategy.STRATEGY, require_sentiment_feed=False)
    )
    monkeypatch.setattr(
        strategy,
        "analyze_market_sentiment",
        lambda _symbol: pytest.fail("news should come from the cycle snapshot"),
    )

    signal = strategy.generate_signal(
        "EURUSD", h1, h4, sentiment=SentimentReading(0.0, 0, None, None, feed_available=True)
    )

    assert signal.direction == TradeDirection.BUY


def test_session_blackout_rollover_and_weekend() -> None:
    from datetime import datetime, timezone
    from strategy import is_session_blackout

    # Wednesday 12:00 UTC -> should NOT be blackout
    wed_noon = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    blocked, _ = is_session_blackout(wed_noon)
    assert not blocked

    # Wednesday 22:05 UTC -> rollover blackout
    wed_rollover = datetime(2026, 10, 14, 22, 5, tzinfo=timezone.utc)
    blocked, reason = is_session_blackout(wed_rollover)
    assert blocked
    assert "Rollover" in reason

    # Friday 21:30 UTC -> weekend blackout
    fri_night = datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc)
    blocked, reason = is_session_blackout(fri_night)
    assert blocked
    assert "Weekend" in reason

    # Saturday -> weekend blackout
    sat = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)
    blocked, reason = is_session_blackout(sat)
    assert blocked
    assert "Saturday" in reason
