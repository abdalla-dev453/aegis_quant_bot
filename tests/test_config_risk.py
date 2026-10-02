from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_config_check(**overrides: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in (
        "RISK_PER_TRADE_PCT",
        "MAX_DAILY_LOSS_PCT",
        "MAX_DRAWDOWN_FROM_PEAK_PCT",
        "MAX_TRADES_PER_DAY",
        "MAX_CONCURRENT_POSITIONS",
    ):
        environment.pop(name, None)
    environment.update(overrides)
    server_dir = str(Path(__file__).resolve().parents[1] / "server")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (server_dir, environment.get("PYTHONPATH", "")) if path
    )
    return subprocess.run(
        [sys.executable, "-c", "from config import RISK; RISK.validate()"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_risk_limits_load_from_environment() -> None:
    result = _run_config_check(
        RISK_PER_TRADE_PCT="0.25",
        MAX_DAILY_LOSS_PCT="1.0",
        MAX_DRAWDOWN_FROM_PEAK_PCT="2.0",
        MAX_TRADES_PER_DAY="3",
        MAX_CONCURRENT_POSITIONS="2",
    )

    assert result.returncode == 0, result.stderr


def test_invalid_environment_risk_limit_fails_validation() -> None:
    result = _run_config_check(RISK_PER_TRADE_PCT="0")

    assert result.returncode != 0
    assert "RISK_PER_TRADE_PCT must be greater than 0" in result.stderr


def test_non_finite_environment_risk_multiplier_fails_validation() -> None:
    result = _run_config_check(ATR_SL_MULTIPLIER="nan")

    assert result.returncode != 0
    assert "ATR_SL_MULTIPLIER must be finite" in result.stderr