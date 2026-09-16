"""Pure strategy gates: no MT5 terminal or network connection is required."""

from __future__ import annotations

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


def test_generate_signal_requires_sentiment_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    h1 = _frame(1.11, 1.10, (54.0, 56.0))
    h4 = _frame(1.12, 1.10, (50.0, 50.0))
    monkeypatch.setattr(
        strategy,
        "analyze_market_sentiment",
        lambda _symbol: SentimentReading(0.8, 1, None, None),
    )

    signal = strategy.generate_signal("EURUSD", h1, h4)

    assert signal.direction == TradeDirection.BUY
