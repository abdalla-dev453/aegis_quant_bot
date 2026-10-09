"""Thread-safe runtime snapshots shared by the trading loop and API."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

_lock = Lock()
_CONTROL_STATE_FILE = Path(os.getenv("CONTROL_STATE_FILE", "control_state.json"))
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
        "changedAt": datetime.now(UTC).isoformat(),
        "revision": 0,
    },
    "started_at": datetime.now(UTC).isoformat(),
}


def _restore_control() -> None:
    if not _CONTROL_STATE_FILE.exists():
        _snapshot["control"].update(
            status="PAUSED",
            entriesAllowed=False,
            managementAllowed=True,
            reason="Operator re-arm required after startup reconciliation",
            source="STARTUP_RECOVERY",
        )
        return
    try:
        state = json.loads(_CONTROL_STATE_FILE.read_text(encoding="utf-8"))
        status = str(state["status"]).upper()
        if status not in {"RUNNING", "PAUSED", "HALTED"}:
            raise ValueError("invalid control status")
        # A previously running process must come back paused until an
        # operator explicitly re-arms it after broker-state reconciliation.
        restored = "PAUSED" if status == "RUNNING" else status
        _snapshot["control"].update(
            status=restored,
            entriesAllowed=False,
            managementAllowed=restored != "HALTED",
            reason="Process restarted; operator re-arm required" if restored == "PAUSED" else state.get("reason"),
            source="RESTART_RECOVERY",
            changedAt=_timestamp(),
            revision=int(state.get("revision", 0)) + 1,
        )
    except Exception as exc:
        raise RuntimeError("control_state.json is corrupt; restore verified state before startup") from exc


def _persist_control(control: dict[str, Any]) -> None:
    temporary = _CONTROL_STATE_FILE.with_suffix(_CONTROL_STATE_FILE.suffix + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8") as state_file:
        json.dump(control, state_file)
        state_file.flush()
        os.fsync(state_file.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(_CONTROL_STATE_FILE)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


_restore_control()


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
                "id": f"{datetime.now(UTC).timestamp():.6f}",
                "time": datetime.now(UTC).strftime("%H:%M:%S"),
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
        updated = {
            **control,
            "revision": int(control.get("revision", 0)) + 1,
            "status": normalized,
            "entriesAllowed": normalized == "RUNNING",
            "managementAllowed": normalized != "HALTED",
            "reason": reason,
            "source": source,
            "changedAt": _timestamp(),
        }
        try:
            _persist_control(updated)
        except OSError:
            # If durable persistence fails, fail closed in this process even
            # though the operator action cannot be committed to disk.
            control.update(
                status="HALTED",
                entriesAllowed=False,
                managementAllowed=False,
                reason="Control-state persistence failed; manual recovery required",
                source="PERSISTENCE_FAILURE",
                revision=updated["revision"],
                changedAt=_timestamp(),
            )
            raise
        control.update(updated)
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
