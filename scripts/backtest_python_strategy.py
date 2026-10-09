"""Cost-aware, chronological research harness for the Python H1/H4 strategy.

This is a strategy research aid, not a full-bot or broker simulator. It uses MT5-exported candle CSVs,
conservative same-bar stop-first handling, explicit spread/slippage/commission,
and reports train and out-of-sample periods separately. It does not model the
LLM proposal/confidence/volume gate, news, portfolio checks, swaps, partial
fills, trailing stops, or broker-specific execution constraints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "trading-engine"))
from config import INDICATORS
from strategy import compute_indicators


def _load_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if "time" not in frame or not {"open", "high", "low", "close"}.issubset(frame.columns):
        raise ValueError(f"{path} must have time, open, high, low, close columns")
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    if frame.empty:
        raise ValueError(f"{path} contains no valid candles")
    return frame.reset_index(drop=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _period_metrics(trades: list[dict[str, Any]], start_equity: float) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "net_pnl": 0.0,
            "return_pct": 0.0,
            "profit_factor": None,
            "expectancy": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "sharpe_daily_annualized": None,
            "sortino_daily_annualized": None,
            "max_consecutive_losses": 0,
            "monthly_net_pnl": {},
            "top_three_wins_share_pct": None,
        }
    equity = start_equity
    peak = equity
    worst_dd = 0.0
    wins = losses = 0.0
    for trade in trades:
        pnl = float(trade["net_pnl"])
        equity += pnl
        peak = max(peak, equity)
        worst_dd = max(worst_dd, (peak - equity) / peak * 100.0 if peak else 0.0)
        if pnl > 0:
            wins += pnl
        elif pnl < 0:
            losses += abs(pnl)
    daily_pnl: dict[str, float] = {}
    monthly_pnl: dict[str, float] = {}
    consecutive_losses = max_consecutive_losses = 0
    gross_wins = sum(float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0)
    for trade in trades:
        pnl = float(trade["net_pnl"])
        day = str(trade["exit_time"])[:10]
        month = day[:7]
        daily_pnl[day] = daily_pnl.get(day, 0.0) + pnl
        monthly_pnl[month] = monthly_pnl.get(month, 0.0) + pnl
        consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
        max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
    daily_returns: list[float] = []
    running_equity = start_equity
    for day_pnl in daily_pnl.values():
        daily_returns.append(day_pnl / running_equity if running_equity else 0.0)
        running_equity += day_pnl
    returns = pd.Series(daily_returns, dtype="float64")
    daily_std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    downside = returns[returns < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    top_three_wins = sum(sorted((float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0), reverse=True)[:3])
    return {
        "trades": len(trades),
        "net_pnl": round(equity - start_equity, 2),
        "return_pct": round((equity / start_equity - 1) * 100.0, 3) if start_equity else 0.0,
        "profit_factor": round(wins / losses, 4) if losses else (None if not wins else "inf"),
        "expectancy": round(sum(float(t["net_pnl"]) for t in trades) / len(trades), 2),
        "max_drawdown_pct": round(worst_dd, 3),
        "win_rate_pct": round(sum(float(t["net_pnl"]) > 0 for t in trades) / len(trades) * 100, 2),
        "sharpe_daily_annualized": round(float(returns.mean()) / daily_std * math.sqrt(252), 4) if daily_std > 0 else None,
        "sortino_daily_annualized": round(float(returns.mean()) / downside_std * math.sqrt(252), 4) if downside_std > 0 else None,
        "max_consecutive_losses": max_consecutive_losses,
        "monthly_net_pnl": {month: round(pnl, 2) for month, pnl in sorted(monthly_pnl.items())},
        "top_three_wins_share_pct": round(top_three_wins / gross_wins * 100, 2) if gross_wins else None,
    }


def _simulate(
    h1: pd.DataFrame,
    h4: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    equity: float,
    risk_pct: float,
    point: float,
    tick_size: float,
    tick_value: float,
    spread_points: float,
    slippage_points: float,
    commission_per_lot: float,
    volume_step: float,
    min_volume: float,
    max_volume: float,
    stop_atr: float,
    target_atr: float,
    price_basis: str,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    side = 0
    entry = stop = target = lots = 0.0
    opened_at: pd.Timestamp | None = None
    spread = spread_points * point
    slippage = slippage_points * point
    half_spread_cost = spread / 2 + slippage
    first = max(2, int(h1["time"].searchsorted(start)))
    last = min(len(h1), int(h1["time"].searchsorted(end)))
    for idx in range(first, last):
        bar = h1.iloc[idx]
        exited_this_bar = False
        if side:
            bar_high = float(bar.high) + (spread if price_basis == "bid" and side < 0 else 0.0)
            bar_low = float(bar.low) + (spread if price_basis == "bid" and side < 0 else 0.0)
            stop_hit = bar_low <= stop if side > 0 else bar_high >= stop
            target_hit = bar_high >= target if side > 0 else bar_low <= target
            if stop_hit or target_hit:
                # If both are touched within one candle, assume the adverse stop filled first.
                exit_mid = stop if stop_hit else target
                exit_price = exit_mid - side * (slippage if price_basis == "bid" else half_spread_cost)
                gross = (exit_price - entry) * side / tick_size * tick_value * lots
                net = gross - 2 * commission_per_lot * lots
                trades.append({"entry_time": opened_at.isoformat() if opened_at is not None else "", "exit_time": bar.time.isoformat(), "side": "BUY" if side > 0 else "SELL", "lots": lots, "entry": entry, "exit": exit_price, "exit_reason": "stop" if stop_hit else "target", "net_pnl": round(net, 2)})
                equity += net
                side = 0
                exited_this_bar = True
        if side or exited_this_bar:
            continue
        h4_idx = int((h4["time"] + pd.Timedelta(hours=4)).searchsorted(bar.time, side="right") - 1)
        if h4_idx < 0:
            continue
        # Use the most recent fully closed H4 indicator row, never an in-progress candle.
        h1_row = h1.iloc[idx - 1]
        prev_row = h1.iloc[idx - 2]
        h4_row = h4.iloc[h4_idx]
        if any(pd.isna(v) for v in (h1_row.ema_50, h1_row.ema_200, h1_row.rsi, h1_row.atr, prev_row.rsi, h4_row.ema_50, h4_row.ema_200)):
            continue
        fast_col, slow_col = f"ema_{INDICATORS.ema_fast}", f"ema_{INDICATORS.ema_slow}"
        if h4_row[fast_col] > h4_row[slow_col] and h1_row[fast_col] > h1_row[slow_col] and 52 <= h1_row.rsi < INDICATORS.rsi_overbought and h1_row.rsi > prev_row.rsi:
            side = 1
        elif h4_row[fast_col] < h4_row[slow_col] and h1_row[fast_col] < h1_row[slow_col] and INDICATORS.rsi_oversold < h1_row.rsi <= 48 and h1_row.rsi < prev_row.rsi:
            side = -1
        else:
            continue
        atr = float(h1_row.atr)
        raw_entry = float(bar.open)
        if price_basis == "bid":
            entry = raw_entry + (spread + slippage if side > 0 else -slippage)
        else:
            entry = raw_entry + side * half_spread_cost
        stop_distance = atr * stop_atr
        target_distance = atr * target_atr
        stop = entry - side * stop_distance
        target = entry + side * target_distance
        risk_cash = equity * risk_pct / 100.0
        risk_per_lot = stop_distance / tick_size * tick_value
        if risk_per_lot <= 0:
            side = 0
            continue
        lots = min(max_volume, math.floor((risk_cash / risk_per_lot) / volume_step) * volume_step)
        if lots < min_volume:
            side = 0
            continue
        opened_at = bar.time
        # Apply the newly opened trade to this candle too. If OHLC cannot tell
        # which level traded first, take the stop to avoid optimistic bias.
        bar_high = float(bar.high) + (spread if price_basis == "bid" and side < 0 else 0.0)
        bar_low = float(bar.low) + (spread if price_basis == "bid" and side < 0 else 0.0)
        same_bar_stop = bar_low <= stop if side > 0 else bar_high >= stop
        same_bar_target = bar_high >= target if side > 0 else bar_low <= target
        if same_bar_stop or same_bar_target:
            exit_mid = stop if same_bar_stop else target
            exit_price = exit_mid - side * (slippage if price_basis == "bid" else half_spread_cost)
            gross = (exit_price - entry) * side / tick_size * tick_value * lots
            net = gross - 2 * commission_per_lot * lots
            trades.append({"entry_time": opened_at.isoformat(), "exit_time": bar.time.isoformat(), "side": "BUY" if side > 0 else "SELL", "lots": lots, "entry": entry, "exit": exit_price, "exit_reason": "stop" if same_bar_stop else "target", "net_pnl": round(net, 2)})
            equity += net
            side = 0
    if side and opened_at is not None and last > first:
        final_bar = h1.iloc[last - 1]
        if price_basis == "bid":
            exit_price = float(final_bar.close) - side * slippage + (spread if side < 0 else 0.0)
        else:
            exit_price = float(final_bar.close) - side * half_spread_cost
        gross = (exit_price - entry) * side / tick_size * tick_value * lots
        net = gross - 2 * commission_per_lot * lots
        trades.append({"entry_time": opened_at.isoformat(), "exit_time": final_bar.time.isoformat(), "side": "BUY" if side > 0 else "SELL", "lots": lots, "entry": entry, "exit": exit_price, "exit_reason": "period_end", "net_pnl": round(net, 2)})
    return trades


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h1", required=True, type=Path, help="MT5 H1 CSV: time,open,high,low,close")
    parser.add_argument("--h4", required=True, type=Path, help="MT5 H4 CSV: time,open,high,low,close")
    parser.add_argument("--output", type=Path, default=Path("backtest_report.json"))
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--risk-pct", type=float, default=0.25)
    parser.add_argument("--point", type=float, required=True)
    parser.add_argument("--tick-size", type=float, required=True)
    parser.add_argument("--tick-value", type=float, required=True)
    parser.add_argument("--spread-points", type=float, required=True)
    parser.add_argument("--slippage-points", type=float, required=True)
    parser.add_argument("--commission-per-lot", type=float, required=True)
    parser.add_argument("--volume-step", type=float, default=0.01)
    parser.add_argument("--min-volume", type=float, default=0.01)
    parser.add_argument("--max-volume", type=float, default=50.0)
    parser.add_argument("--stop-atr", type=float, default=1.5)
    parser.add_argument("--target-atr", type=float, default=3.0)
    parser.add_argument("--price-basis", choices=("bid", "mid"), default="bid", help="OHLC quote basis; MT5 exports are usually bid-based")
    parser.add_argument("--train-fraction", type=float, default=0.7)
    args = parser.parse_args()
    positive = (args.equity, args.risk_pct, args.point, args.tick_size, args.tick_value, args.volume_step, args.min_volume, args.max_volume, args.stop_atr, args.target_atr)
    nonnegative = (args.spread_points, args.slippage_points, args.commission_per_lot)
    if any(not math.isfinite(value) or value <= 0 for value in positive) or any(not math.isfinite(value) or value < 0 for value in nonnegative) or args.max_volume < args.min_volume or not 0.5 <= args.train_fraction < 1:
        parser.error("equity/risk/price/volume/ATR values must be positive; costs nonnegative; volume range valid; train-fraction in [0.5, 1)")
    h1_raw, h4_raw = _load_csv(args.h1), _load_csv(args.h4)
    h1, h4 = compute_indicators(h1_raw.set_index("time")), compute_indicators(h4_raw.set_index("time"))
    if h1.empty or h4.empty:
        parser.error("not enough H1/H4 history to warm up EMA/RSI/ATR indicators")
    h1 = h1.reset_index(names="time")
    h4 = h4.reset_index(names="time")
    split = h1.time.iloc[int(len(h1) * args.train_fraction)]
    common = {
        "equity": args.equity,
        "risk_pct": args.risk_pct,
        "point": args.point,
        "tick_size": args.tick_size,
        "tick_value": args.tick_value,
        "spread_points": args.spread_points,
        "slippage_points": args.slippage_points,
        "commission_per_lot": args.commission_per_lot,
        "volume_step": args.volume_step,
        "min_volume": args.min_volume,
        "max_volume": args.max_volume,
        "stop_atr": args.stop_atr,
        "target_atr": args.target_atr,
        "price_basis": args.price_basis,
    }
    train = _simulate(h1, h4, h1.time.iloc[0], split, **common)
    test = _simulate(h1, h4, split, h1.time.iloc[-1] + pd.Timedelta(hours=1), **common)
    report = {
        "strategy": "closed H1/H4 EMA50/200 + RSI14 confirmation; ATR stop/target",
        "data": {"h1": str(args.h1), "h4": str(args.h4), "h1_sha256": _sha256(args.h1), "h4_sha256": _sha256(args.h4), "h1_rows": len(h1), "h4_rows": len(h4), "train_end_utc": split.isoformat(), "test_start_utc": split.isoformat()},
        "assumptions": {"price_basis": args.price_basis, "spread_points": args.spread_points, "slippage_points": args.slippage_points, "commission_per_lot_per_side": args.commission_per_lot, "risk_pct": args.risk_pct, "same_bar_rule": "stop first", "limitations": ["does not model LLM proposal/confidence/volume", "no news blackout", "no portfolio checks", "no swaps", "no trailing stops", "no partial fills", "no broker-specific stop/freeze/session behavior", "not a Strategy Tester substitute"]},
        "train": _period_metrics(train, args.equity),
        "out_of_sample": _period_metrics(test, args.equity),
        "trades": train + test,
        "warning": "Research evidence only; validate data and assumptions against MT5 Strategy Tester and broker demo before any deployment.",
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "train": report["train"], "out_of_sample": report["out_of_sample"]}, indent=2))


if __name__ == "__main__":
    main()
