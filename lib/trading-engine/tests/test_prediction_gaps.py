"""Tests for prediction engine fallback behavior and pattern detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
from prediction_engine import (
    PatternRecognitionEngine,
    PredictionDirection,
    PricePredictionEngine,
    VolatilityForecaster,
)


def _make_df(rows: int = 100, trend: str = "up") -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="h")
    np.random.seed(42)
    prices = np.linspace(1.10, 1.12 if trend == "up" else 1.08, rows)
    noise = np.random.normal(0, 0.001, rows)
    closes = prices + noise
    df = pd.DataFrame({
        "open": closes - 0.0001,
        "high": closes + 0.001,
        "low": closes - 0.001,
        "close": closes,
        "volume": np.random.randint(50, 150, rows),
    }, index=idx)
    return df


class TestPricePredictionFallback:
    def test_fallback_with_insufficient_data(self):
        engine = PricePredictionEngine()
        engine.ml_enabled = False
        df = _make_df(10)
        result = engine.predict_price_move(df)
        assert result.direction == PredictionDirection.SIDEWAYS
        assert result.confidence == 0.0

    def test_fallback_bullish_on_rising_ema(self):
        engine = PricePredictionEngine()
        engine.ml_enabled = False
        df = _make_df(100, "up")
        df["ema_50"] = df["close"].ewm(span=50).mean()
        df["ema_200"] = df["close"].ewm(span=200).mean()
        df["atr"] = df["close"].pct_change().rolling(14).std()
        df["rsi"] = 60.0
        df = df.dropna()
        result = engine.predict_price_move(df)
        assert result.direction == PredictionDirection.UP

    def test_fallback_bearish_on_falling_ema(self):
        engine = PricePredictionEngine()
        engine.ml_enabled = False
        df = _make_df(100, "down")
        df["ema_50"] = df["close"].ewm(span=50).mean()
        df["ema_200"] = df["close"].ewm(span=200).mean()
        df["atr"] = df["close"].pct_change().rolling(14).std()
        df["rsi"] = 40.0
        df = df.dropna()
        result = engine.predict_price_move(df)
        assert result.direction == PredictionDirection.DOWN


class TestPatternRecognition:
    def test_no_patterns_on_short_data(self):
        engine = PatternRecognitionEngine()
        df = _make_df(20)
        patterns = engine.detect_patterns(df)
        assert patterns == []

    def test_returns_filtered_by_confidence(self):
        engine = PatternRecognitionEngine()
        df = _make_df(100, "up")
        patterns = engine.detect_patterns(df)
        for p in patterns:
            assert p.confidence >= 0.7


class TestVolatilityForecaster:
    def test_forecast_with_sufficient_data(self):
        forecaster = VolatilityForecaster()
        df = _make_df(100)
        result = forecaster.forecast_volatility(df)
        assert result.expected_volatility > 0.0
        assert result.breakout_probability >= 0.0
        assert result.breakout_probability <= 1.0

    def test_default_forecast_on_insufficient_data(self):
        forecaster = VolatilityForecaster()
        df = _make_df(30)
        result = forecaster.forecast_volatility(df)
        assert result.volatility_regime in ("low", "normal", "high", "unknown")

    def test_regime_classification(self):
        forecaster = VolatilityForecaster()
        df = _make_df(200)
        result = forecaster.forecast_volatility(df)
        assert result.volatility_regime != "unknown"
