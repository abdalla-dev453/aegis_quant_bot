"""Risk-guard unit tests; all external MT5 calls are replaced with fakes."""

from __future__ import annotations

from types import SimpleNamespace

import execution
from strategy import TradeDirection


def test_correlated_same_direction_exposure_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(execution, "mt5", SimpleNamespace(POSITION_TYPE_BUY=0))
    positions = [SimpleNamespace(symbol="EURUSD.a", type=0)]

    assert execution.is_correlated_exposure_blocked("GBPUSD", TradeDirection.BUY, positions)
    assert not execution.is_correlated_exposure_blocked("GBPUSD", TradeDirection.SELL, positions)


def test_peak_drawdown_latches_until_manual_reset(monkeypatch) -> None:
    values = iter((1000.0, 900.0, 900.0, 900.0, 900.0))
    monkeypatch.setattr(execution, "get_account_equity", lambda: next(values))
    monkeypatch.setattr(execution, "_peak_equity", None)
    monkeypatch.setattr(execution, "_peak_equity_halted", False)

    assert not execution.check_max_drawdown_guard()
    assert execution.check_max_drawdown_guard()
    assert execution.check_max_drawdown_guard()
    execution.reset_max_drawdown_guard()
    assert not execution.risk_guard_status()["peakDrawdownHalted"]
