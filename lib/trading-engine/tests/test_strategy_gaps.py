"""Tests for indicator computation, trend logic, and signal gates."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import strategy
from strategy import (
    SentimentReading,
    TradeDirection,
    Trend,
    compute_indicators,
    generate_signal,
    get_multi_timeframe_trend,
    get_trend,
    has_multi_timeframe_ema_rsi_confirmation,
    is_news_blackout,
    rsi_filter_ok,
)


def _make_prices(rows: int, start: float = 1.10) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="h")
    drift = np.linspace(0, 0.02, rows)
    closes = start + drift + np.random.RandomState(42).normal(0, 0.001, rows)
    highs = closes + 0.001
    lows = closes - 0.001
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": 100},
        index=idx,
    )


class TestComputeIndicators:
    def test_returns_empty_on_none(self) -> None:
        assert compute_indicators(None).empty

    def test_returns_empty_on_missing_columns(self) -> None:
        df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0]})
        assert compute_indicators(df).empty

    def test_returns_empty_on_too_few_rows(self) -> None:
        df = pd.DataFrame(
            {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
        )
        assert compute_indicators(df).empty

    def test_returns_empty_on_all_nan_ohlc(self) -> None:
        df = pd.DataFrame(
            {
                "open": [np.nan, np.nan],
                "high": [np.nan, np.nan],
                "low": [np.nan, np.nan],
                "close": [np.nan, np.nan],
            }
        )
        assert compute_indicators(df).empty

    def test_adds_all_indicator_columns(self) -> None:
        df = _make_prices(300)
        result = compute_indicators(df)
        assert not result.empty
        assert f"ema_{strategy.INDICATORS.ema_fast}" in result.columns
        assert f"ema_{strategy.INDICATORS.ema_slow}" in result.columns
        assert "rsi" in result.columns
        assert "atr" in result.columns
        assert not result["ema_50"].isna().any()
        assert not result["rsi"].isna().any()


class TestGetTrend:
    def test_bullish_when_fast_above_slow(self) -> None:
        df = pd.DataFrame({"ema_50": [1.10, 1.12], "ema_200": [1.11, 1.10]})
        assert get_trend(df) == Trend.BULLISH

    def test_bearish_when_fast_below_slow(self) -> None:
        df = pd.DataFrame({"ema_50": [1.09, 1.08], "ema_200": [1.11, 1.10]})
        assert get_trend(df) == Trend.BEARISH

    def test_neutral_on_nan(self) -> None:
        df = pd.DataFrame({"ema_50": [np.nan], "ema_200": [1.10]})
        assert get_trend(df) == Trend.NEUTRAL

    def test_neutral_on_empty(self) -> None:
        assert get_trend(pd.DataFrame()) == Trend.NEUTRAL


class TestMultiTimeframeTrend:
    def test_neutral_when_h4_is_neutral(self) -> None:
        h1 = pd.DataFrame({"ema_50": [1.12], "ema_200": [1.10]})
        h4 = pd.DataFrame({"ema_50": [1.10], "ema_200": [1.10]})
        assert get_multi_timeframe_trend(h1, h4) == Trend.NEUTRAL

    def test_confirmed_bullish(self) -> None:
        h1 = pd.DataFrame({"ema_50": [1.12], "ema_200": [1.10]})
        h4 = pd.DataFrame({"ema_50": [1.13], "ema_200": [1.11]})
        assert get_multi_timeframe_trend(h1, h4) == Trend.BULLISH

    def test_h1_against_h4_is_neutral(self) -> None:
        h1 = pd.DataFrame({"ema_50": [1.08], "ema_200": [1.10]})
        h4 = pd.DataFrame({"ema_50": [1.13], "ema_200": [1.11]})
        assert get_multi_timeframe_trend(h1, h4) == Trend.NEUTRAL


class TestRsiFilter:
    def test_rejects_empty(self) -> None:
        assert not rsi_filter_ok(pd.DataFrame(), Trend.BULLISH)

    def test_bullish_ok_with_rising_rsi(self) -> None:
        df = pd.DataFrame({"rsi": [50.0, 55.0]})
        assert rsi_filter_ok(df, Trend.BULLISH)

    def test_bullish_blocks_overbought(self) -> None:
        df = pd.DataFrame({"rsi": [50.0, 75.0]})
        assert not rsi_filter_ok(df, Trend.BULLISH)

    def test_bearish_ok_with_falling_rsi(self) -> None:
        df = pd.DataFrame({"rsi": [50.0, 45.0]})
        assert rsi_filter_ok(df, Trend.BEARISH)

    def test_bearish_blocks_oversold(self) -> None:
        df = pd.DataFrame({"rsi": [50.0, 25.0]})
        assert not rsi_filter_ok(df, Trend.BEARISH)


class TestMultiTimeframeConfirmation:
    def test_requires_rsi_boost_for_bullish(self) -> None:
        h1 = pd.DataFrame(
            {"ema_50": [1.12, 1.13], "ema_200": [1.10, 1.10], "rsi": [40.0, 45.0]}
        )
        h4 = pd.DataFrame(
            {"ema_50": [1.13, 1.14], "ema_200": [1.11, 1.11], "rsi": [40.0, 45.0]}
        )
        assert not has_multi_timeframe_ema_rsi_confirmation(h1, h4, Trend.BULLISH)

    def test_requires_rsi_drop_for_bearish(self) -> None:
        h1 = pd.DataFrame(
            {"ema_50": [1.07, 1.06], "ema_200": [1.10, 1.10], "rsi": [60.0, 55.0]}
        )
        h4 = pd.DataFrame(
            {"ema_50": [1.08, 1.07], "ema_200": [1.11, 1.11], "rsi": [60.0, 55.0]}
        )
        assert not has_multi_timeframe_ema_rsi_confirmation(h1, h4, Trend.BEARISH)


class TestNewsBlackout:
    def test_blackout_just_before_event(self) -> None:
        reading = SentimentReading(0.0, 1, "NFP", 5, next_event_impact="HIGH")
        assert is_news_blackout(reading) is True

    def test_blackout_after_event(self) -> None:
        reading = SentimentReading(0.0, 1, "CPI", -10, next_event_impact="HIGH")
        assert is_news_blackout(reading) is True

    def test_no_blackout_outside_window(self) -> None:
        reading = SentimentReading(0.0, 1, "NFP", 31, next_event_impact="HIGH")
        assert is_news_blackout(reading) is False

    def test_no_blackout_for_low_impact(self) -> None:
        reading = SentimentReading(0.0, 1, "Retail Sales", 5, next_event_impact="LOW")
        assert is_news_blackout(reading) is False

    def test_no_blackout_when_no_event(self) -> None:
        reading = SentimentReading(0.0, 0, None, None)
        assert is_news_blackout(reading) is False


class TestGenerateSignal:
    def _df(self, fast: float, slow: float, rsi_last: float, rsi_prev: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ema_50": [fast, fast],
                "ema_200": [slow, slow],
                "rsi": [rsi_prev, rsi_last],
                "atr": [0.001, 0.001],
            }
        )

    def test_insufficient_data(self) -> None:
        signal = generate_signal("EURUSD", pd.DataFrame(), pd.DataFrame())
        assert signal.direction == TradeDirection.NONE

    def test_degenerate_atr_blocks(self) -> None:
        h1 = self._df(1.12, 1.10, 55.0, 53.0).assign(atr=[0.0, 0.0])
        h4 = self._df(1.13, 1.11, 50.0, 50.0)
        signal = generate_signal("EURUSD", h1, h4)
        assert signal.direction == TradeDirection.NONE
        assert "ATR" in signal.reason

    def test_unavailable_sentiment_blocks_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h1 = self._df(1.12, 1.10, 55.0, 53.0)
        h4 = self._df(1.13, 1.11, 50.0, 50.0)
        monkeypatch.setattr(
            strategy,
            "analyze_market_sentiment",
            lambda _s: SentimentReading(0.0, 0, None, None, feed_available=False),
        )
        signal = generate_signal("EURUSD", h1, h4)
        assert signal.direction == TradeDirection.NONE
        assert "unavailable" in signal.reason.lower()
