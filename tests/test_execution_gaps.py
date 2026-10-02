"""Tests for execution.py: lot sizing, SL/TP math, and trade guards."""

from __future__ import annotations

from types import SimpleNamespace

import execution
import pytest
from execution import (
    OrderError,
    calculate_lot_size,
    calculate_sl_tp,
)
from strategy import TradeDirection

_ORIGINAL_GET_SYMBOL = execution._get_symbol


def _make_sym(**overrides):
    defaults = {
        "info": SimpleNamespace(digits=5, volume_min=0.01, volume_max=100, point=0.0001),
        "tick_size": 0.0001,
        "tick_value": 10.0,
        "step": 0.01,
        "step_decimals": 2,
        "min_stop_points": 0.001,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _fake_mt5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution, "mt5", SimpleNamespace(
        POSITION_TYPE_BUY=0,
        ORDER_TYPE_BUY=1,
        ORDER_TYPE_SELL=2,
        TRADE_ACTION_DEAL=0,
        TRADE_RETCODE_DONE=0,
        TRADE_RETCODE_REQUOTE=1,
        ORDER_FILLING_IOC=0,
        ORDER_TIME_GTC=0,
        account_info=lambda: SimpleNamespace(equity=10000, balance=10000, margin=0, margin_free=10000, margin_level=1000),
        symbol_info_tick=lambda _s: SimpleNamespace(ask=1.1, bid=1.0),
        order_calc_margin=lambda *_: 100.0,
    ))
    monkeypatch.setattr(execution, "require_mt5_runtime", lambda: None)
    monkeypatch.setattr(execution, "ensure_connected", lambda: None)
    monkeypatch.setattr(execution, "get_account_equity", lambda: 10000.0)
    monkeypatch.setattr(execution, "_get_symbol", lambda _s: _make_sym())


class TestLotSize:
    def test_symbol_metadata_refreshes_after_ttl(self, monkeypatch):
        current_time = [100.0]
        lookups = []
        first_info = SimpleNamespace(
            trade_tick_size=0.0001,
            trade_tick_value=10.0,
            point=0.0001,
            volume_step=0.01,
            trade_stops_level=10,
        )
        refreshed_info = SimpleNamespace(
            trade_tick_size=0.0001,
            trade_tick_value=20.0,
            point=0.0001,
            volume_step=0.01,
            trade_stops_level=20,
        )

        monkeypatch.setattr(execution, "_symbol_cache", {})
        monkeypatch.setattr(execution, "_get_symbol", _ORIGINAL_GET_SYMBOL)
        monkeypatch.setattr(execution.time, "monotonic", lambda: current_time[0])
        monkeypatch.setattr(
            execution.mt5,
            "symbol_info",
            lambda _symbol: lookups.append(True) or (first_info if len(lookups) == 1 else refreshed_info),
            raising=False,
        )

        initial = execution._get_symbol("EURUSD")
        current_time[0] += execution._SYMBOL_CACHE_TTL_SECONDS + 1
        refreshed = execution._get_symbol("EURUSD")

        assert initial.tick_value == 10.0
        assert refreshed.tick_value == 20.0
        assert refreshed.min_stop_points == 0.002
        assert len(lookups) == 2

    def test_basic_lot_size(self, monkeypatch):
        lots = calculate_lot_size("EURUSD", 0.0050)
        assert 0.01 <= lots <= 100.0

    def test_zero_sl_distance_raises(self):
        with pytest.raises(OrderError):
            calculate_lot_size("EURUSD", 0.0)

    def test_negative_sl_distance_raises(self):
        with pytest.raises(OrderError):
            calculate_lot_size("EURUSD", -1.0)

    def test_lot_snapped_to_step(self):
        lots = calculate_lot_size("EURUSD", 0.0100)
        assert lots * 100 == int(lots * 100)

    def test_lot_clamped_to_min(self, monkeypatch):
        monkeypatch.setattr(execution, "_get_symbol", lambda _s: _make_sym(
            info=SimpleNamespace(digits=5, volume_min=0.10, volume_max=100, point=0.0001),
            step=0.01,
        ))
        lots = calculate_lot_size("EURUSD", 0.0050)
        assert lots >= 0.10

    def test_lot_clamped_to_max(self, monkeypatch):
        monkeypatch.setattr(execution, "_get_symbol", lambda _s: _make_sym(
            info=SimpleNamespace(digits=5, volume_min=0.01, volume_max=1.0, point=0.0001),
            tick_value=10.0,
            step=0.01,
        ))
        monkeypatch.setattr(execution, "get_account_equity", lambda: 500000.0)
        lots = calculate_lot_size("EURUSD", 0.0010)
        assert lots <= 1.0

    def test_below_minimum_volume_is_rejected_to_preserve_risk(self, monkeypatch):
        monkeypatch.setattr(execution, "get_account_equity", lambda: 1.0)

        with pytest.raises(OrderError, match="below broker minimum"):
            calculate_lot_size("EURUSD", 0.0050)

    def test_sell_margin_check_uses_sell_order_type(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            execution.mt5,
            "order_calc_margin",
            lambda order_type, *_: calls.append(order_type) or 100.0,
        )

        calculate_lot_size("EURUSD", 0.0050, TradeDirection.SELL)

        assert calls == [execution.mt5.ORDER_TYPE_SELL]


class TestSLTP:
    def test_buy_sl_below_entry_tp_above(self):
        sl, tp = calculate_sl_tp("EURUSD", TradeDirection.BUY, 1.1000, 0.0050)
        assert sl < 1.1000
        assert tp > 1.1000

    def test_sell_sl_above_entry_tp_below(self):
        sl, tp = calculate_sl_tp("EURUSD", TradeDirection.SELL, 1.1000, 0.0050)
        assert sl > 1.1000
        assert tp < 1.1000

    def test_none_direction_raises(self):
        with pytest.raises(OrderError):
            calculate_sl_tp("EURUSD", TradeDirection.NONE, 1.1000, 0.0050)


class TestTradeGuards:
    def test_halt_on_max_concurrent(self, monkeypatch):
        monkeypatch.setattr(execution, "control_state", lambda: {"status": "RUNNING", "entriesAllowed": True})
        monkeypatch.setattr(execution, "check_daily_loss_guard", lambda: False)
        monkeypatch.setattr(execution, "check_max_drawdown_guard", lambda: False)
        monkeypatch.setattr(execution, "check_max_trades_guard", lambda: True)
        monkeypatch.setattr(execution, "is_correlated_exposure_blocked", lambda *a, **k: False)
        monkeypatch.setattr(execution, "get_open_positions", lambda **kw: list(range(5)))
        monkeypatch.setattr(execution, "calculate_lot_size", lambda *a, **k: 0.1)
        monkeypatch.setattr(execution, "calculate_sl_tp", lambda *a, **k: (1.0, 1.1))
        monkeypatch.setattr(execution, "RISK", SimpleNamespace(
            max_concurrent_positions=3,
            max_trades_per_day=10,
        ))
        monkeypatch.setattr(execution, "EXECUTION", SimpleNamespace(mode="paper", live_orders_enabled=False))
        result = execution.place_order("EURUSD", TradeDirection.BUY, 0.001, "test")
        assert result is None

    def test_daily_loss_guard_blocks(self, monkeypatch):
        monkeypatch.setattr(execution, "control_state", lambda: {"status": "RUNNING", "entriesAllowed": True})
        monkeypatch.setattr(execution, "check_daily_loss_guard", lambda: True)
        monkeypatch.setattr(execution, "check_max_drawdown_guard", lambda: False)
        monkeypatch.setattr(execution, "check_max_trades_guard", lambda: False)
        result = execution.place_order("EURUSD", TradeDirection.BUY, 0.001, "test")
        assert result is None
