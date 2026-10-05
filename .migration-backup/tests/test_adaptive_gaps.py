"""Tests for adaptive_optimization parameter adjustments and persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import adaptive_optimization
import pytest
from adaptive_optimization import (
    AdaptiveOptimizer,
    AdjustmentDirection,
    PerformanceMetrics,
    get_all_effective_parameters,
    get_effective_param,
)


class TestParameterOverrides:
    def test_default_returns_config_value(self):
        from config import RISK
        assert get_effective_param("risk_per_trade_pct", 1.5) == RISK.risk_per_trade_pct

    def test_override_persists_across_calls(self):
        adaptive_optimization._parameter_overrides["risk_per_trade_pct"] = 0.5
        assert get_effective_param("risk_per_trade_pct", 1.5) == 0.5
        assert get_all_effective_parameters()["risk_per_trade_pct"] == 0.5
        del adaptive_optimization._parameter_overrides["risk_per_trade_pct"]


class TestPerformanceAnalysis:
    def test_empty_metrics_when_no_orders(self):
        opt = AdaptiveOptimizer()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("adaptive_optimization.read", lambda: {"orders": []})
        metrics = opt.analyze_recent_performance()
        assert metrics.total_trades == 0
        monkeypatch.undo()

    def test_metrics_calculation(self):
        opt = AdaptiveOptimizer()
        opt.min_trades_for_optimization = 3
        monkeypatch = pytest.MonkeyPatch()
        orders = [
            {"pnl": 100.0, "timestamp": datetime.now(timezone.utc).isoformat()},
            {"pnl": -50.0, "timestamp": datetime.now(timezone.utc).isoformat()},
            {"pnl": 200.0, "timestamp": datetime.now(timezone.utc).isoformat()},
        ]
        monkeypatch.setattr("adaptive_optimization.read", lambda: {"orders": orders})
        metrics = opt.analyze_recent_performance()
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.total_profit == 300.0
        assert metrics.total_loss == 50.0
        monkeypatch.undo()


class TestAdjustmentLogic:
    def test_low_win_rate_tightens_criteria(self):
        opt = AdaptiveOptimizer()
        opt.current_parameters = {
            "rsi_overbought": 70.0,
            "rsi_oversold": 30.0,
            "sentiment_bullish_threshold": 0.5,
            "sentiment_bearish_threshold": -0.5,
            "risk_per_trade_pct": 1.5,
            "atr_sl_multiplier": 1.5,
            "atr_tp_multiplier": 3.0,
        }
        metrics = PerformanceMetrics(
            total_trades=20,
            winning_trades=5,
            losing_trades=15,
            win_rate=0.25,
            total_profit=500.0,
            total_loss=1000.0,
            profit_factor=0.5,
            average_win=100.0,
            average_loss=-66.7,
            max_drawdown=0.05,
            sharpe_ratio=0.5,
            period_start=datetime.now(timezone.utc) - timedelta(days=7),
            period_end=datetime.now(timezone.utc),
        )
        adjustments = opt.determine_adjustments(metrics)
        assert len(adjustments) > 0
        rsi_adj = [a for a in adjustments if a.parameter_name == "rsi_overbought"]
        assert len(rsi_adj) == 1
        assert rsi_adj[0].direction == AdjustmentDirection.INCREASE

    def test_high_win_rate_loosens_criteria(self):
        opt = AdaptiveOptimizer()
        opt.current_parameters = {
            "rsi_overbought": 75.0,
            "rsi_oversold": 25.0,
            "sentiment_bullish_threshold": 0.5,
            "sentiment_bearish_threshold": -0.5,
            "risk_per_trade_pct": 1.5,
            "atr_sl_multiplier": 1.5,
            "atr_tp_multiplier": 3.0,
        }
        metrics = PerformanceMetrics(
            total_trades=20,
            winning_trades=16,
            losing_trades=4,
            win_rate=0.80,
            total_profit=1600.0,
            total_loss=400.0,
            profit_factor=4.0,
            average_win=100.0,
            average_loss=-100.0,
            max_drawdown=0.03,
            sharpe_ratio=2.0,
            period_start=datetime.now(timezone.utc) - timedelta(days=7),
            period_end=datetime.now(timezone.utc),
        )
        adjustments = opt.determine_adjustments(metrics)
        assert len(adjustments) > 0
        rsi_adj = [a for a in adjustments if a.parameter_name == "rsi_overbought"]
        assert len(rsi_adj) == 1
        assert rsi_adj[0].direction == AdjustmentDirection.DECREASE

    def test_insufficient_trades_no_adjustments(self):
        opt = AdaptiveOptimizer()
        metrics = PerformanceMetrics(
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            total_profit=300.0,
            total_loss=200.0,
            profit_factor=1.5,
            average_win=100.0,
            average_loss=-100.0,
            max_drawdown=0.02,
            sharpe_ratio=1.0,
            period_start=datetime.now(timezone.utc) - timedelta(days=7),
            period_end=datetime.now(timezone.utc),
        )
        adjustments = opt.determine_adjustments(metrics)
        assert len(adjustments) == 0


class TestOptimizationCycle:
    def test_disabled_returns_disabled_status(self):
        import pytest
        monkeypatch = pytest.MonkeyPatch()
        opt = AdaptiveOptimizer()
        monkeypatch.setattr(opt, "enabled", False)
        result = opt.run_optimization_cycle()
        assert result["status"] == "disabled"
        assert result["adjustments_made"] == 0
        monkeypatch.undo()

    def test_insufficient_data_cycle(self):
        opt = AdaptiveOptimizer()
        result = opt.run_optimization_cycle()
        assert result["status"] in ("insufficient_data", "disabled")
