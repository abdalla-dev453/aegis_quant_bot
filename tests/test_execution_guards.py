"""Risk-guard unit tests; all external MT5 calls are replaced with fakes."""

from __future__ import annotations

from types import SimpleNamespace

import data_provider
import execution
import runtime_state
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


def test_place_order_respects_runtime_control(monkeypatch) -> None:
    def fake_asdict(self):
        return {"order": 1, "retcode": 0, "price": 1.1, "comment": "ok"}

    monkeypatch.setattr(execution, "mt5", SimpleNamespace(
        POSITION_TYPE_BUY=0,
        ORDER_TYPE_BUY=1,
        ORDER_TYPE_SELL=2,
        TRADE_ACTION_DEAL=0,
        ORDER_TIME_GTC=0,
        ORDER_FILLING_IOC=0,
        TRADE_RETCODE_DONE=0,
        order_check=lambda _: SimpleNamespace(retcode=0, comment="ok"),
        order_send=lambda _: SimpleNamespace(order=1, retcode=0, price=1.1, comment="ok", _asdict=fake_asdict),
        orders_get=lambda: [],
        symbol_info_tick=lambda _: SimpleNamespace(ask=1.1, bid=1.0),
        last_error=lambda: "",
        account_info=lambda: SimpleNamespace(equity=1000, balance=1000, margin=100, margin_free=900, margin_level=1000),
        symbol_info=lambda _: SimpleNamespace(digits=5, volume_min=0.01, volume_max=100, trade_stops_level=10, trade_freeze_level=0, trade_mode=True),
    ))
    monkeypatch.setattr(execution, "ensure_connected", lambda: None)
    monkeypatch.setattr(execution, "get_open_positions", lambda **_: [])
    monkeypatch.setattr(execution, "calculate_lot_size", lambda *a, **k: 0.1)
    monkeypatch.setattr(execution, "calculate_sl_tp", lambda *a, **k: (1.0, 1.1))
    monkeypatch.setattr(execution, "check_daily_loss_guard", lambda: False)
    monkeypatch.setattr(execution, "check_max_drawdown_guard", lambda: False)
    monkeypatch.setattr(execution, "check_max_trades_guard", lambda: False)
    monkeypatch.setattr(execution, "_record_filled_trade", lambda: None)
    monkeypatch.setattr(execution, "control_state", runtime_state.control_state)
    monkeypatch.setattr(data_provider, "validate_symbol_trade_constraints", lambda *_, **__: None)
    monkeypatch.setattr(
        execution,
        "_get_symbol",
        lambda _: SimpleNamespace(
            info=SimpleNamespace(digits=5, volume_min=0.01, volume_max=100),
            tick_size=0.0001,
            tick_value=10.0,
            step=0.01,
            step_decimals=2,
            min_stop_points=0.001,
        ),
    )

    runtime_state.set_control("PAUSED", reason="test pause", source="pytest")

    result = execution.place_order("EURUSD", TradeDirection.BUY, 0.001, "test")

    assert result is None
    assert runtime_state.control_state()["status"] == "PAUSED"

    runtime_state.set_control("RUNNING", reason="", source="pytest")
    result = execution.place_order("EURUSD", TradeDirection.BUY, 0.001, "test")
    assert result is not None


def test_close_bot_positions_reports_broker_results(monkeypatch) -> None:
    positions = [
        SimpleNamespace(ticket=11, symbol="EURUSD", volume=0.1, type=0),
        SimpleNamespace(ticket=12, symbol="GBPUSD", volume=0.2, type=1),
    ]
    requests = []
    results = iter((
        SimpleNamespace(retcode=100, comment="closed"),
        SimpleNamespace(retcode=999, comment="market closed"),
    ))
    monkeypatch.setattr(execution, "ensure_connected", lambda: None)
    monkeypatch.setattr(execution, "get_open_positions", lambda **_: positions)
    monkeypatch.setattr(execution, "mt5", SimpleNamespace(
        POSITION_TYPE_BUY=0,
        TRADE_ACTION_DEAL=1,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        ORDER_TIME_GTC=0,
        ORDER_FILLING_IOC=0,
        TRADE_RETCODE_DONE=100,
        TRADE_RETCODE_DONE_PARTIAL=101,
        symbol_info_tick=lambda _: SimpleNamespace(bid=1.1, ask=1.2),
        order_send=lambda request: (requests.append(request), next(results))[1],
        last_error=lambda: "",
    ))

    result = execution.close_bot_positions()

    assert result == {
        "closed": ["11"],
        "failed": [{"ticket": "12", "error": "market closed"}],
    }
    assert requests[0]["type"] == execution.mt5.ORDER_TYPE_SELL
    assert requests[0]["price"] == 1.1
    assert requests[1]["type"] == execution.mt5.ORDER_TYPE_BUY
    assert requests[1]["price"] == 1.2


def test_trailing_stops_do_not_mutate_positions_in_paper_mode(monkeypatch) -> None:
    monkeypatch.setattr(execution, "EXECUTION", SimpleNamespace(live_orders_enabled=False))
    monkeypatch.setattr(
        execution,
        "ensure_connected",
        lambda: (_ for _ in ()).throw(AssertionError("paper mode must not connect for trailing updates")),
    )

    execution.manage_trailing_stops()


def test_trailing_stops_respect_halted_control(monkeypatch) -> None:
    monkeypatch.setattr(execution, "EXECUTION", SimpleNamespace(live_orders_enabled=True))
    monkeypatch.setattr(execution, "control_state", lambda: {"status": "HALTED", "managementAllowed": False})
    monkeypatch.setattr(
        execution,
        "ensure_connected",
        lambda: (_ for _ in ()).throw(AssertionError("HALTED must not connect for trailing updates")),
    )

    execution.manage_trailing_stops()

