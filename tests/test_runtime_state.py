"""Runtime state snapshot and control-store unit tests."""

from __future__ import annotations

import pytest

import runtime_state


def test_control_starts_running_and_entries_allowed() -> None:
    runtime_state.set_control("RUNNING", reason="", source="test")
    control = runtime_state.control_state()
    assert control["status"] == "RUNNING"
    assert control["entriesAllowed"] is True
    assert control["managementAllowed"] is True
    assert control["revision"] >= 0


@pytest.mark.parametrize("status", ["RUNNING", "PAUSED", "HALTED"])
def test_set_control_updates_status_and_permissions(status: str) -> None:
    runtime_state.set_control(status, reason="test", source="pytest")
    control = runtime_state.control_state()
    assert control["status"] == status
    assert control["entriesAllowed"] is (status == "RUNNING")
    assert control["managementAllowed"] is (status != "HALTED")
    assert control["reason"] == "test"
    assert control["source"] == "pytest"
    assert control["revision"] >= 1


def test_set_control_rejects_invalid_status() -> None:
    with pytest.raises(ValueError):
        runtime_state.set_control("STOPPED")


def test_record_proposal_updates_last_signal() -> None:
    runtime_state.update(last_signal={})
    proposal = {"symbol": "EURUSD", "action": "BUY", "status": "received"}
    runtime_state.record_proposal(proposal)
    state = runtime_state.read()
    assert state["last_signal"] == proposal
    assert any(p["symbol"] == "EURUSD" for p in state["proposals"])


def test_record_order_updates_trade_analysis() -> None:
    before = runtime_state.read()["trade_analysis"]["summary"]["totalTrades"]
    runtime_state.record_order(
        {
            "ticket": 1,
            "symbol": "EURUSD",
            "direction": "BUY",
            "fill_price": 1.1000,
            "volume": 0.1,
            "sl": 1.0950,
            "tp": 1.1050,
            "atr": 0.001,
            "reason": "test",
            "pnl": 50.0,
        }
    )
    state = runtime_state.read()
    assert state["trade_analysis"]["summary"]["totalTrades"] == before + 1
    assert state["trade_analysis"]["summary"]["netPnl"] == 50.0
    assert any(t["ticket"] == 1 for t in state["trade_analysis"]["recentTrades"])


def test_read_returns_deep_copy() -> None:
    runtime_state.set_control("RUNNING", reason="", source="pytest")
    state1 = runtime_state.read()
    state1["control"]["status"] = "PAUSED"
    assert runtime_state.control_state()["status"] == "RUNNING"
