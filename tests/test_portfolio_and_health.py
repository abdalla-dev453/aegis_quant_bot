"""Tests for portfolio_risk_manager.py, data_quality, and main loop utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import main
from portfolio_risk_manager import (
    CurrencyExposure,
    PortfolioAnalysis,
    PortfolioHealth,
    PortfolioRiskManager,
    RiskAlert,
    RiskType,
)
from self_healing import DataQualityChecker


class TestPortfolioRisk:
    def setup_method(self) -> None:
        self.mgr = PortfolioRiskManager()

    def test_empty_portfolio_when_no_positions(self, monkeypatch):
        monkeypatch.setattr(self.mgr, "_calculate_total_exposure", lambda _: 0.0)
        monkeypatch.setattr(self.mgr, "_analyze_currency_exposures", lambda *_: [])
        monkeypatch.setattr(self.mgr, "_calculate_correlation_risk", lambda _: 0.0)
        monkeypatch.setattr(self.mgr, "_calculate_concentration_risk", lambda *_, **__: 0.0)
        monkeypatch.setattr(self.mgr, "_calculate_volatility_risk", lambda _: 0.0)
        monkeypatch.setattr(self.mgr, "_generate_risk_alerts", lambda *a: [])
        monkeypatch.setattr(self.mgr, "_determine_portfolio_health", lambda *a: PortfolioHealth.HEALTHY)
        monkeypatch.setattr(self.mgr, "_generate_recommendations", lambda *a, **k: [])
        monkeypatch.setattr(self.mgr, "_generate_risk_summary", lambda *a, **k: "ok")
        result = self.mgr.analyze_portfolio()
        assert result.total_exposure_usd == 0.0
        assert result.equity == 0.0

    def test_exposure_percentage_calculation(self):
        analysis = PortfolioAnalysis(
            overall_health=PortfolioHealth.HEALTHY,
            total_exposure_usd=5000.0,
            exposure_percentage=50.0,
            equity=10000.0,
            currency_exposures=[],
            correlation_risk_score=0.0,
            concentration_risk_score=0.0,
            volatility_risk_score=0.0,
            alerts=[],
            risk_summary="ok",
            recommended_actions=[],
            timestamp=datetime.now(timezone.utc),
        )
        assert analysis.exposure_percentage == 50.0
        assert analysis.equity == 10000.0

    def test_risk_alert_fields(self):
        alert = RiskAlert(
            risk_type=RiskType.EXPOSURE,
            severity="high",
            message="test",
            current_value=15.0,
            threshold_value=10.0,
            timestamp=datetime.now(timezone.utc),
            recommended_action="reduce",
        )
        assert alert.risk_type == RiskType.EXPOSURE
        assert alert.severity == "high"
        assert alert.current_value == 15.0

    def test_currency_exposure_net_direction_long(self):
        exp = CurrencyExposure("EUR", 5000.0, 50.0, 3, "long")
        assert exp.net_direction == "long"

    def test_currency_exposure_net_direction_neutral(self):
        exp = CurrencyExposure("EUR", 5000.0, 50.0, 2, "neutral")
        assert exp.net_direction == "neutral"


class TestDataQualityChecker:
    def setup_method(self) -> None:
        self.checker = DataQualityChecker()

    def test_rejects_empty_dataframe(self):
        import pandas as pd
        valid, msg = self.checker.validate_dataframe(pd.DataFrame(), "TEST")
        assert not valid
        assert "empty" in msg.lower()

    def test_rejects_insufficient_rows(self):
        import pandas as pd
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        valid, msg = self.checker.validate_dataframe(df, "TEST")
        assert not valid
        assert "insufficient" in msg.lower()

    def test_rejects_high_nan_ratio(self):
        import numpy as np
        import pandas as pd
        data = [{"close": float(i) if i % 3 != 0 else np.nan} for i in range(100)]
        df = pd.DataFrame(data)
        valid, msg = self.checker.validate_dataframe(df, "TEST")
        assert not valid
        assert "nan" in msg.lower()

    def test_rejects_inf_values(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({"close": [float(i) if i < 99 else np.inf for i in range(100)]})
        valid, msg = self.checker.validate_dataframe(df, "TEST")
        assert not valid
        assert "infinite" in msg.lower()

    def test_rejects_duplicate_timestamps(self):
        import pandas as pd
        idx = pd.DatetimeIndex([pd.Timestamp("2024-01-01")] * 60)
        df = pd.DataFrame({"close": [float(i) for i in range(60)]}, index=idx)
        valid, msg = self.checker.validate_dataframe(df, "TEST")
        assert not valid
        assert "duplicate" in msg.lower()

    def test_valid_dataframe_passes(self):
        import pandas as pd
        idx = pd.DatetimeIndex(pd.date_range("2024-01-01", periods=100, freq="h"))
        df = pd.DataFrame({"close": [float(i) * 0.01 for i in range(100)]}, index=idx)
        valid, _msg = self.checker.validate_dataframe(df, "TEST")
        assert valid

    def test_price_data_rejects_high_below_low(self):
        import pandas as pd
        df = pd.DataFrame({
            "open": [1.0, 1.1],
            "high": [1.05, 1.0],  # high < low on row 2 -> invalid
            "low": [0.95, 1.2],
            "close": [1.0, 1.1],
        })
        valid, _msg = self.checker.validate_price_data(df)
        assert not valid


class TestLastCandleTracker:
    def test_first_candle_is_new(self):
        import pandas as pd
        tracker = main.LastCandleTracker()
        ts = pd.Timestamp("2024-01-01 10:00")
        assert tracker.is_new_candle("EURUSD", ts)
        tracker.mark_seen("EURUSD", ts)
        assert not tracker.is_new_candle("EURUSD", ts)

    def test_progressing_candle_is_new(self):
        import pandas as pd
        tracker = main.LastCandleTracker()
        ts1 = pd.Timestamp("2024-01-01 10:00")
        ts2 = pd.Timestamp("2024-01-01 11:00")
        tracker.mark_seen("EURUSD", ts1)
        assert tracker.is_new_candle("EURUSD", ts2)
        assert not tracker.is_new_candle("EURUSD", ts1)

    def test_symbols_independent(self):
        import pandas as pd
        tracker = main.LastCandleTracker()
        ts = pd.Timestamp("2024-01-01 10:00")
        tracker.mark_seen("EURUSD", ts)
        assert tracker.is_new_candle("GBPUSD", ts)


class TestErrorBackoff:
    def test_success_resets_consecutive(self):
        backoff = main.ErrorBackoff()
        backoff.record_failure()
        backoff.record_failure()
        backoff.record_success()
        assert backoff._consecutive == 0

    def test_exponential_backoff_growth(self):
        backoff = main.ErrorBackoff()
        d1 = backoff.record_failure()
        d2 = backoff.record_failure()
        d3 = backoff.record_failure()
        assert d2 > d1
        assert d3 > d2

    def test_backoff_capped(self):
        backoff = main.ErrorBackoff()
        from config import MAX_BACKOFF_SECONDS
        for _ in range(20):
            delay = backoff.record_failure()
        assert delay <= MAX_BACKOFF_SECONDS


class TestPortfolioRiskCheckPreTrade:
    def test_disables_when_portfolio_risk_off(self, monkeypatch):
        from portfolio_risk_manager import portfolio_risk_manager
        monkeypatch.setattr(
            "portfolio_risk_manager.ADVANCED_RISK",
            SimpleNamespace(enable_portfolio_risk=False),
        )
        allowed, reason = portfolio_risk_manager.check_pre_trade_risk("EURUSD", "BUY", 0.1)
        assert allowed
        assert "disabled" in reason.lower()

    def test_analysis_failure_blocks_pre_trade(self, monkeypatch):
        import portfolio_risk_manager as portfolio_module

        manager = PortfolioRiskManager()

        def fail_connection():
            raise RuntimeError("simulated MT5 outage")

        monkeypatch.setattr(portfolio_module, "ensure_connected", fail_connection)

        allowed, reason = manager.check_pre_trade_risk("EURUSD", "BUY", 0.1)

        assert not allowed
        assert "risk analysis unavailable" in reason.lower()
