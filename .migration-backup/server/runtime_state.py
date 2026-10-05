"""Thread-safe runtime snapshots shared by the trading loop and API."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_lock = Lock()
_snapshot: dict[str, Any] = {
    "connected": False,
    "last_signal": {},
    "logs": [],
    "proposals": [],
    "orders": [],
    "trade_analysis": {"summary": {"totalTrades": 0, "netPnl": 0.0}, "recentTrades": []},
    "last_cycle": None,
    "last_fault": None,
    "control": {
        "status": "RUNNING",
        "entriesAllowed": True,
        "managementAllowed": True,
        "reason": None,
        "source": "STARTUP",
        "changedAt": datetime.now(timezone.utc).isoformat(),
        "revision": 0,
    },
    "started_at": datetime.now(timezone.utc).isoformat(),
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def update(**values: Any) -> None:
    with _lock:
        for key, value in values.items():
            _snapshot[key] = deepcopy(value)


def read() -> dict[str, Any]:
    with _lock:
        result = deepcopy(_snapshot)
        result["logs"] = list(_snapshot.get("logs", []))
        return result


def add_log(level: str, message: str) -> None:
    with _lock:
        logs = _snapshot.setdefault("logs", [])
        logs.append(
            {
                "id": f"{datetime.now(timezone.utc).timestamp():.6f}",
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            }
        )
        del logs[:-200]


def set_control(status: str, reason: str | None = None, source: str = "OPERATOR") -> dict[str, Any]:
    normalized = status.upper()
    if normalized not in {"RUNNING", "PAUSED", "HALTED"}:
        raise ValueError("Control status must be RUNNING, PAUSED, or HALTED")
    with _lock:
        control = _snapshot["control"]
        control["revision"] = int(control.get("revision", 0)) + 1
        control.update(
            {
                "status": normalized,
                "entriesAllowed": normalized == "RUNNING",
                "managementAllowed": normalized != "HALTED",
                "reason": reason,
                "source": source,
                "changedAt": _timestamp(),
            }
        )
        return deepcopy(control)


def control_state() -> dict[str, Any]:
    with _lock:
        return deepcopy(_snapshot["control"])


def record_proposal(proposal: dict[str, Any]) -> None:
    with _lock:
        proposals = _snapshot.setdefault("proposals", [])
        proposals.append(deepcopy(proposal))
        del proposals[:-100]
        _snapshot["last_signal"] = deepcopy(proposal)


def record_order(order: dict[str, Any]) -> None:
    with _lock:
        orders = _snapshot.setdefault("orders", [])
        orders.append(deepcopy(order))
        del orders[:-100]
        analysis = _snapshot.setdefault("trade_analysis", {})
        recent = analysis.setdefault("recentTrades", [])
        recent.append(deepcopy(order))
        del recent[:-50]
        summary = analysis.setdefault("summary", {"totalTrades": 0, "netPnl": 0.0})
        summary["totalTrades"] = int(summary.get("totalTrades", 0)) + 1
        summary["netPnl"] = float(summary.get("netPnl", 0.0)) + float(order.get("pnl", 0.0) or 0.0)


def record_cycle(cycle: dict[str, Any]) -> None:
    update(last_cycle=deepcopy(cycle))


def record_fault(fault: dict[str, Any]) -> None:
    update(last_fault=deepcopy(fault))
    add_log("ERROR", str(fault.get("message", "Runtime fault")))

