"""
execution.py
------------
Everything that touches order placement and open-position management.
Position sizing math is broker-aware (uses symbol_info for tick value /
tick size / volume step rather than hardcoded pip values), because a fixed
"$10 per pip per lot" assumption breaks silently on JPY pairs, metals, and
indices.
"""

from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import math
import os
import threading
import time
from collections import namedtuple
from pathlib import Path
from queue import Empty, Queue
from typing import Any, cast

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - Linux/test environment only.
    mt5 = cast(Any, None)

from config import EXECUTION, RISK, SYMBOL_CORRELATIONS
from data_provider import (
    ensure_connected,
    get_account_equity,
    get_open_positions,
    mt5_operation_lock,
    mt5_serialized,
)
from metrics import ORDERS_PLACED
from runtime_state import add_log, control_state, set_control
from strategy import TradeDirection

logger = logging.getLogger("trading_bot.execution")


def require_mt5_runtime() -> None:
    if mt5 is None:
        raise OrderError(
            "MetaTrader5 is not available in this runtime. This bot must run inside a "
            "Windows MT5 terminal with a live broker login."
        )


def close_bot_positions() -> dict[str, list[dict[str, str]] | list[str]]:
    """Close positions managed by this bot and report individual failures."""
    require_mt5_runtime()
    ensure_connected()
    closed: list[str] = []
    failed: list[dict[str, str]] = []

    with mt5_operation_lock():
        positions = get_open_positions(magic=RISK.magic_number)
        for position in positions:
            ticket = str(position.ticket)
            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                failed.append({"ticket": ticket, "error": f"No price available for {position.symbol}"})
                continue

            is_buy = position.type == mt5.POSITION_TYPE_BUY
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "position": position.ticket,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if is_buy else tick.ask,
                "deviation": max(int(RISK.deviation_points), 20),
                "magic": RISK.magic_number,
                "comment": "Aegis operator close-all",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                closed.append(ticket)
            else:
                detail = result.comment if result is not None else str(mt5.last_error())
                if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE_PARTIAL:
                    detail = detail or "Broker only partially closed position"
                    reason = (
                        f"Partial close for position {ticket} ({position.symbol}); "
                        "broker reconciliation required before new entries"
                    )
                    set_control("PAUSED", reason=reason, source="PARTIAL_CLOSE_RECOVERY")
                    add_log("ERROR", reason)
                    detail = f"{detail}; {reason}"
                failed.append({"ticket": ticket, "error": detail or "Broker rejected close request"})

    return {"closed": closed, "failed": failed}


# ---------------------------------------------------------------------------
# Non-blocking async logger (QueueHandler + background worker thread)
# Decouples disk I/O from the hot trading loop — enqueue cost is ~µs.
# ---------------------------------------------------------------------------
_logger_queue: Queue = Queue(maxsize=2000)


class _QueueHandler(logging.Handler):
    """Drop-on-floor handler: if the queue is full, the log record is lost
    rather than blocking the trading thread."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _logger_queue.put_nowait(record)
        except Exception:  # noqa: BLE001,S110 - never block the hot path
            pass


def _log_worker() -> None:
    """Background daemon that drains the queue and writes to handlers."""
    file_handler = logging.handlers.RotatingFileHandler(
        "execution.log", maxBytes=5_000_000, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    while True:
        try:
            record = _logger_queue.get(timeout=1)
            file_handler.emit(record)
        except Empty:
            continue


_log_thread = threading.Thread(target=_log_worker, daemon=True)
_log_thread.start()
logger.addHandler(_QueueHandler())
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Symbol-info cache (thread-safe, bounded LRU)
# Avoids repeated mt5.symbol_info() IPC calls for the same symbol on every
# tick — one call per symbol per cache lifetime instead.
# ---------------------------------------------------------------------------
_SymbolData = namedtuple(
    "_SymbolData",
    "info tick_size tick_value step step_decimals min_stop_points",
)

_symbol_cache: dict[str, tuple[_SymbolData, float]] = {}
_cache_lock = threading.Lock()
_MAX_CACHE_SIZE = 128
_SYMBOL_CACHE_TTL_SECONDS = 300


def _get_symbol(symbol: str) -> _SymbolData:
    """Return short-lived cached metadata; refresh broker specs every five minutes."""
    require_mt5_runtime()
    now = time.monotonic()
    with _cache_lock:
        cached = _symbol_cache.get(symbol)
        if cached is not None:
            data, cached_at = cached
            if now - cached_at < _SYMBOL_CACHE_TTL_SECONDS:
                return data
            _symbol_cache.pop(symbol, None)

    ensure_connected()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise OrderError(f"symbol_info returned None for {symbol}")

    tick_size = info.trade_tick_size or info.point
    tick_value = getattr(info, "trade_tick_value_loss", 0.0) or info.trade_tick_value
    step = info.volume_step or 0.01
    step_decimals = max(0, -math.floor(math.log10(step)))
    min_stop_points = max(info.trade_stops_level, 1) * info.point

    sym = _SymbolData(
        info=info,
        tick_size=tick_size,
        tick_value=tick_value,
        step=step,
        step_decimals=step_decimals,
        min_stop_points=min_stop_points,
    )
    with _cache_lock:
        if len(_symbol_cache) >= _MAX_CACHE_SIZE:
            _symbol_cache.pop(next(iter(_symbol_cache)))  # simple FIFO eviction
        _symbol_cache[symbol] = (sym, now)
    return sym


def invalidate_symbol_cache(symbol: str | None = None) -> None:
    """Call after broker reconnect or symbol config change."""
    with _cache_lock:
        if symbol:
            _symbol_cache.pop(symbol, None)
        else:
            _symbol_cache.clear()


class OrderError(RuntimeError):
    pass


# Absolute guardrails — hard ceilings that override any config value.
MAX_SINGLE_ORDER_LOTS = 50.0  # never send an order larger than this
MAX_MARGIN_UTILIZATION_PCT = 80.0  # refuse trades that would push margin use past this

_POSITION_STATE_FILE = Path("position_state.json")
_position_state_lock = threading.Lock()
_original_risk_by_position: dict[int, float] = {}


def _load_position_state() -> None:
    global _original_risk_by_position
    if _POSITION_STATE_FILE.exists():
        try:
            with open(_POSITION_STATE_FILE, "r") as state_file:
                _original_risk_by_position = {
                    int(ticket): float(risk) for ticket, risk in json.load(state_file).items()
                }
        except Exception as exc:
            logger.critical("Position state is corrupt; refusing startup: %s", exc)
            raise RuntimeError("position_state.json is corrupt; restore a verified state file before trading") from exc



def _save_position_state() -> None:
    with _position_state_lock:
        temporary_file = _POSITION_STATE_FILE.with_suffix(_POSITION_STATE_FILE.suffix + ".tmp")
        temporary_file.parent.mkdir(parents=True, exist_ok=True)
        with temporary_file.open("w", encoding="utf-8") as state_file:
            json.dump(_original_risk_by_position, state_file)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.chmod(temporary_file, 0o600)
        temporary_file.replace(_POSITION_STATE_FILE)


def _record_original_risk(position_id: int, risk_distance: float) -> None:
    with _position_state_lock:
        _original_risk_by_position[position_id] = risk_distance
    _save_position_state()


def _get_original_risk(position_id: int, fallback: float) -> float:
    with _position_state_lock:
        return _original_risk_by_position.get(position_id, fallback)


def _position_identifier_from_result(result: Any, symbol: str) -> int | None:
    """Resolve the stable MT5 position identifier through the fill deal."""
    deal_ticket = int(getattr(result, "deal", 0) or 0)
    if not deal_ticket:
        return None
    try:
        deals = mt5.history_deals_get(ticket=deal_ticket)
    except (AttributeError, TypeError):
        return None
    if not deals:
        return None
    for deal in deals:
        position_id = int(getattr(deal, "position_id", 0) or 0)
        if position_id and getattr(deal, "symbol", symbol) == symbol:
            return position_id
    return None


def _record_fill_risk_or_halt(result: Any, symbol: str, risk_distance: float) -> bool:
    """Persist risk by stable position ID, halting entries if mapping fails."""
    position_id = _position_identifier_from_result(result, symbol)
    if position_id is None:
        reason = (
            f"Filled {symbol} order {getattr(result, 'order', 0)} could not be mapped "
            "to a stable position identifier; broker reconciliation required"
        )
        logger.critical(reason)
        add_log("ERROR", reason)
        set_control("PAUSED", reason=reason, source="POSITION_RECONCILIATION")
        return False
    try:
        _record_original_risk(position_id, risk_distance)
    except OSError as exc:
        reason = f"Filled {symbol} position {position_id} risk state could not be persisted: {exc}"
        logger.critical(reason)
        add_log("ERROR", reason)
        set_control("PAUSED", reason=reason, source="POSITION_RECONCILIATION")
        return False
    return True


_daily_guard_lock = threading.RLock()
_day_start_equity: float | None = None
_day_start_date: datetime.date | None = None
_trading_halted_today = False
_trades_today = 0
_trades_today_date: datetime.date | None = None
_peak_equity: float | None = None
_peak_equity_halted = False
_week_start_equity: float | None = None
_week_start_date: datetime.date | None = None
_weekly_halted = False
_RISK_STATE_FILE = Path(os.getenv("RISK_STATE_FILE", "risk_guard_state.json"))
_KILL_SWITCH_FILE = Path(os.getenv("KILL_SWITCH_FILE", "emergency.kill"))


def _persist_risk_state() -> None:
    """Atomically persist loss latches and counters so a restart cannot re-arm."""
    with _daily_guard_lock:
        payload = {
            "day_start_date": _day_start_date.isoformat() if _day_start_date else None,
            "day_start_equity": _day_start_equity,
            "trading_halted_today": _trading_halted_today,
            "trades_today_date": _trades_today_date.isoformat() if _trades_today_date else None,
            "trades_today": _trades_today,
            "peak_equity": _peak_equity,
            "peak_equity_halted": _peak_equity_halted,
            "week_start_date": _week_start_date.isoformat() if _week_start_date else None,
            "week_start_equity": _week_start_equity,
            "weekly_halted": _weekly_halted,
        }
        temporary_file = _RISK_STATE_FILE.with_suffix(_RISK_STATE_FILE.suffix + ".tmp")
        temporary_file.parent.mkdir(parents=True, exist_ok=True)
        with temporary_file.open("w", encoding="utf-8") as state_file:
            json.dump(payload, state_file)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.chmod(temporary_file, 0o600)
        temporary_file.replace(_RISK_STATE_FILE)


def _restore_risk_state() -> None:
    global _day_start_date, _day_start_equity, _trading_halted_today
    global _trades_today_date, _trades_today, _peak_equity, _peak_equity_halted
    global _week_start_date, _week_start_equity, _weekly_halted
    if not _RISK_STATE_FILE.exists():
        return
    try:
        with _RISK_STATE_FILE.open(encoding="utf-8") as state_file:
            state = json.load(state_file)
        _day_start_date = datetime.date.fromisoformat(state["day_start_date"]) if state.get("day_start_date") else None
        _day_start_equity = float(state["day_start_equity"]) if state.get("day_start_equity") is not None else None
        _trading_halted_today = bool(state.get("trading_halted_today", False))
        _trades_today_date = datetime.date.fromisoformat(state["trades_today_date"]) if state.get("trades_today_date") else None
        _trades_today = int(state.get("trades_today", 0))
        _peak_equity = float(state["peak_equity"]) if state.get("peak_equity") is not None else None
        _peak_equity_halted = bool(state.get("peak_equity_halted", False))
        _week_start_date = datetime.date.fromisoformat(state["week_start_date"]) if state.get("week_start_date") else None
        _week_start_equity = float(state["week_start_equity"]) if state.get("week_start_equity") is not None else None
        _weekly_halted = bool(state.get("weekly_halted", False))
        if _trades_today < 0 or (_day_start_equity is not None and _day_start_equity <= 0):
            raise ValueError("invalid persisted risk values")
    except Exception as exc:
        logger.critical("Risk guard state is corrupt; refusing startup: %s", exc)
        raise RuntimeError("risk_guard_state.json is corrupt; restore a verified state before trading") from exc


_restore_risk_state()


def _refresh_daily_guard() -> None:
    global _day_start_equity, _day_start_date, _trading_halted_today, _trades_today, _trades_today_date
    today = datetime.datetime.now(datetime.UTC).date()
    with _daily_guard_lock:
        if _day_start_date != today:
            _day_start_date = today
            _day_start_equity = get_account_equity()
            _trading_halted_today = False
            _trades_today_date, _trades_today = today, 0
            logger.info("Daily risk guard reset. Baseline equity=%.2f", _day_start_equity)
            _persist_risk_state()


def check_daily_loss_guard() -> bool:
    global _trading_halted_today
    _refresh_daily_guard()
    if _trading_halted_today:
        return True
    current_equity = get_account_equity()
    if _day_start_equity and _day_start_equity > 0:
        drawdown_pct = (_day_start_equity - current_equity) / _day_start_equity * 100.0
        if drawdown_pct >= RISK.max_daily_loss_pct:
            with _daily_guard_lock:
                _trading_halted_today = True
                _persist_risk_state()
            logger.error(
                "Daily loss limit hit: %.2f%% (limit %.2f%%). Entries halted for today.",
                drawdown_pct,
                RISK.max_daily_loss_pct,
            )
            add_log("WARN", "Daily loss limit reached; trading blocked")
            return True
    return False


def check_max_drawdown_guard() -> bool:
    """Latch trading after the configured peak-to-equity drawdown is hit."""
    global _peak_equity, _peak_equity_halted
    equity = get_account_equity()
    with _daily_guard_lock:
        if _peak_equity is None or equity > _peak_equity:
            _peak_equity = equity
            _persist_risk_state()
        if _peak_equity_halted:
            return True
        drawdown_pct = (
            (_peak_equity - equity) / _peak_equity * 100.0 if _peak_equity else 0.0
        )
        if drawdown_pct >= RISK.max_drawdown_from_peak_pct:
            _peak_equity_halted = True
            _persist_risk_state()
            logger.error(
                "Peak drawdown limit hit: %.2f%% (limit %.2f%%). Manual reset required.",
                drawdown_pct,
                RISK.max_drawdown_from_peak_pct,
            )
            return True
    return False


def check_weekly_loss_guard() -> bool:
    """Latch entries after UTC Monday-to-now equity loss reaches its cap."""
    global _week_start_date, _week_start_equity, _weekly_halted
    today = datetime.datetime.now(datetime.UTC).date()
    monday = today - datetime.timedelta(days=today.weekday())
    with _daily_guard_lock:
        if _week_start_date != monday or _week_start_equity is None:
            _week_start_date = monday
            _week_start_equity = get_account_equity()
            _weekly_halted = False
            _persist_risk_state()
        if _weekly_halted:
            return True
        equity = get_account_equity()
        loss_pct = (
            (_week_start_equity - equity) / _week_start_equity * 100.0
            if _week_start_equity and _week_start_equity > 0
            else 0.0
        )
        if loss_pct >= RISK.max_weekly_loss_pct:
            _weekly_halted = True
            _persist_risk_state()
            logger.error(
                "Weekly loss limit hit: %.2f%% (limit %.2f%%); entries halted until next UTC week.",
                loss_pct,
                RISK.max_weekly_loss_pct,
            )
            add_log("WARN", "Weekly loss limit reached; trading blocked")
            return True
    return False


def activate_emergency_kill(reason: str = "Independent host kill switch") -> None:
    """Create a host-local kill marker independent of the dashboard/API."""
    temporary = _KILL_SWITCH_FILE.with_suffix(_KILL_SWITCH_FILE.suffix + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8") as kill_file:
        kill_file.write(reason[:500])
        kill_file.flush()
        os.fsync(kill_file.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(_KILL_SWITCH_FILE)


def _apply_host_kill_switch() -> bool:
    if not _KILL_SWITCH_FILE.exists():
        return False
    reason = "Host emergency kill marker is present; remove it only after position reconciliation"
    # Stop fresh entries while leaving normal position management available.
    set_control("PAUSED", reason=reason, source="HOST_KILL_SWITCH")
    add_log("ERROR", reason)
    return True


def reset_max_drawdown_guard() -> None:
    """Manually re-enable entries, establishing the current equity as the new peak."""
    global _peak_equity, _peak_equity_halted
    equity = get_account_equity()
    with _daily_guard_lock:
        _peak_equity = equity
        _peak_equity_halted = False
        _persist_risk_state()
    logger.warning("Peak drawdown guard manually reset. New peak equity=%.2f", equity)


def risk_guard_status() -> dict[str, float | bool | int]:
    """Return the live circuit-breaker state for the monitoring API."""
    equity = get_account_equity()
    with _daily_guard_lock:
        peak = _peak_equity if _peak_equity is not None else equity
        peak_drawdown = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
        return {
            "peakDrawdownPct": max(0.0, peak_drawdown),
            "peakDrawdownHalted": _peak_equity_halted,
            "tradesToday": _trades_today,
            "weeklyLossHalted": _weekly_halted,
            "weekStartEquity": _week_start_equity or 0.0,
        }


def check_max_trades_guard() -> bool:
    _refresh_daily_guard()
    with _daily_guard_lock:
        return _trades_today >= RISK.max_trades_per_day


def _record_filled_trade() -> None:
    global _trades_today
    _refresh_daily_guard()
    with _daily_guard_lock:
        _trades_today += 1
        _persist_risk_state()


def _canonical_symbol(symbol: str) -> str:
    """Map common broker suffixes to the configured base symbol."""
    for candidate in {part for pair in SYMBOL_CORRELATIONS for part in pair}:
        if symbol.upper().startswith(candidate):
            return candidate
    return symbol.upper()


def is_correlated_exposure_blocked(
    symbol: str, direction: TradeDirection, open_positions: list[Any]
) -> bool:
    """Block same-direction entries with a configured, highly correlated exposure."""
    candidate = _canonical_symbol(symbol)
    requested_is_buy = direction == TradeDirection.BUY
    for position in open_positions:
        position_symbol = _canonical_symbol(str(position.symbol))
        pair = tuple(sorted((candidate, position_symbol)))
        correlation = SYMBOL_CORRELATIONS.get(pair, 0.0)
        position_is_buy = position.type == mt5.POSITION_TYPE_BUY
        if (
            candidate != position_symbol
            and correlation >= RISK.correlation_threshold
            and requested_is_buy == position_is_buy
        ):
            logger.warning(
                "Skipping %s %s: correlated %s exposure already open (rho=%.2f).",
                symbol, direction.value, position.symbol, correlation,
            )
            return True
    return False


_load_position_state()


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------
def calculate_lot_size(
    symbol: str, sl_distance_price: float, direction: TradeDirection = TradeDirection.BUY
) -> float:
    """
    Position size such that a full stop-out costs exactly
    RISK.risk_per_trade_pct of current account equity.

    lot_size = (equity * risk_pct) / (sl_distance_in_ticks * tick_value)

    Uses the thread-safe symbol cache to avoid repeated IPC calls.
    """
    require_mt5_runtime()
    ensure_connected()
    sym = _get_symbol(symbol)

    if sl_distance_price <= 0:
        raise OrderError(f"Invalid SL distance for {symbol}: {sl_distance_price}")

    if not sym.tick_size or not sym.tick_value:
        raise OrderError(f"Broker did not supply tick size/value for {symbol}")

    equity = get_account_equity()
    risk_amount = equity * (RISK.risk_per_trade_pct / 100.0)

    sl_distance_ticks = sl_distance_price / sym.tick_size
    value_per_lot = sl_distance_ticks * sym.tick_value

    if value_per_lot <= 0:
        raise OrderError(f"Computed non-positive value_per_lot for {symbol}")

    raw_lots = risk_amount / value_per_lot

    # Snap down to the broker's volume step. Never raise a risk-sized order to
    # the broker minimum, because that would exceed the requested risk budget.
    lots = math.floor(raw_lots / sym.step) * sym.step
    if lots < sym.info.volume_min:
        raise OrderError(
            f"Risk-sized volume {lots:.{sym.step_decimals}f} is below broker minimum "
            f"{sym.info.volume_min} for {symbol}; order blocked to preserve risk limit"
        )
    lots = min(sym.info.volume_max, lots)
    lots = round(lots, sym.step_decimals)

    # --- Absolute guardrails ---
    if lots > MAX_SINGLE_ORDER_LOTS:
        raise OrderError(
            f"Computed lot size {lots} exceeds hard ceiling {MAX_SINGLE_ORDER_LOTS} for {symbol}"
        )

    # --- Negative margin protection: use the broker's own calculation ---
    account = mt5.account_info()
    tick = mt5.symbol_info_tick(symbol)
    order_type = mt5.ORDER_TYPE_BUY if direction == TradeDirection.BUY else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == TradeDirection.BUY else tick.bid
    margin_needed = mt5.order_calc_margin(order_type, symbol, lots, price) if tick else None
    if margin_needed is not None and account is not None and account.equity > 0:
        projected = ((account.margin or 0.0) + margin_needed) / account.equity * 100.0
        if projected > MAX_MARGIN_UTILIZATION_PCT:
            raise OrderError(
                f"Margin utilization would reach {projected:.1f}% "
                f"(ceiling {MAX_MARGIN_UTILIZATION_PCT:.0f}%) for {symbol} — order blocked"
            )

    logger.info(
        "Lot sizing %s: equity=%.2f risk_amt=%.2f sl_dist=%.5f -> raw=%.4f lots=%.2f",
        symbol,
        equity,
        risk_amount,
        sl_distance_price,
        raw_lots,
        lots,
    )
    return lots


def calculate_sl_tp(
    symbol: str, direction: TradeDirection, entry_price: float, atr: float
) -> tuple[float, float]:
    """Derive SL/TP purely from ATR, respecting the broker's minimum stop distance."""
    sym = _get_symbol(symbol)

    sl_dist = max(atr * RISK.atr_sl_multiplier, sym.min_stop_points)
    tp_dist = max(atr * RISK.atr_tp_multiplier, sym.min_stop_points)

    if direction == TradeDirection.BUY:
        sl = _snap_price(entry_price - sl_dist, sym.tick_size, "down", sym.info.digits)
        tp = _snap_price(entry_price + tp_dist, sym.tick_size, "up", sym.info.digits)
    elif direction == TradeDirection.SELL:
        sl = _snap_price(entry_price + sl_dist, sym.tick_size, "up", sym.info.digits)
        tp = _snap_price(entry_price - tp_dist, sym.tick_size, "down", sym.info.digits)
    else:
        raise OrderError("calculate_sl_tp called with TradeDirection.NONE")

    return sl, tp


def _snap_price(price: float, tick_size: float, mode: str, digits: int) -> float:
    """Align a price to the broker tick grid, rounding protective levels outward."""
    if tick_size <= 0 or not math.isfinite(price):
        raise OrderError("Invalid price or broker tick size")
    units = price / tick_size
    snapped = math.floor(units + 1e-10) if mode == "down" else math.ceil(units - 1e-10)
    return round(snapped * tick_size, digits)


def _managed_open_risk(positions: list[Any], pending_orders: list[Any]) -> float:
    """Estimate account-currency loss to SL; unknown exposure fails closed."""
    risk = 0.0
    for exposure in [*positions, *pending_orders]:
        stop = float(getattr(exposure, "sl", 0.0) or 0.0)
        volume = float(
            getattr(exposure, "volume", None)
            or getattr(exposure, "volume_current", None)
            or getattr(exposure, "volume_initial", 0.0)
        )
        if stop <= 0 or volume <= 0:
            raise OrderError("Managed open exposure has no valid stop/volume; aggregate risk is unknown")
        symbol = str(exposure.symbol)
        info = _get_symbol(symbol)
        entry = float(getattr(exposure, "price_open", None) or getattr(exposure, "price_current", None) or getattr(exposure, "price_open", 0.0))
        if entry <= 0:
            raise OrderError(f"Managed open exposure for {symbol} has no valid price")
        risk += abs(entry - stop) / info.tick_size * info.tick_value * volume
    return risk


def _retcode_to_text(code: int) -> str:
    """Map common MT5 retcodes to a readable server error label."""
    mapping = {
        mt5.TRADE_RETCODE_DONE: "DONE",
        mt5.TRADE_RETCODE_DONE_PARTIAL: "DONE_PARTIAL",
        mt5.TRADE_RETCODE_ERROR: "ERROR",
        mt5.TRADE_RETCODE_TIMEOUT: "TIMEOUT",
        mt5.TRADE_RETCODE_INVALID: "INVALID",
        mt5.TRADE_RETCODE_INVALID_VOLUME: "INVALID_VOLUME",
        mt5.TRADE_RETCODE_INVALID_PRICE: "INVALID_PRICE",
        mt5.TRADE_RETCODE_INVALID_STOPS: "INVALID_STOPS",
        mt5.TRADE_RETCODE_TRADE_DISABLED: "TRADE_DISABLED",
        mt5.TRADE_RETCODE_MARKET_CLOSED: "MARKET_CLOSED",
        mt5.TRADE_RETCODE_NO_MONEY: "NO_MONEY",
        mt5.TRADE_RETCODE_PRICE_CHANGED: "PRICE_CHANGED",
        mt5.TRADE_RETCODE_OFF_QUOTES: "OFF_QUOTES",
        mt5.TRADE_RETCODE_REQUOTE: "REQUOTE",
        mt5.TRADE_RETCODE_REJECTED: "REJECTED",
        mt5.TRADE_RETCODE_CANCELLED: "CANCELLED",
        mt5.TRADE_RETCODE_CONNECTION: "CONNECTION",
        mt5.TRADE_RETCODE_BUSY: "BUSY",
    }
    return mapping.get(code, f"UNKNOWN_{code}")


# ------------------------------------------------------------------
# Order placement
# ----------------------------------------------------------------
@mt5_serialized
def place_order(
    symbol: str,
    direction: TradeDirection,
    atr: float,
    signal_reason: str = "",
    audit_context: dict[str, Any] | None = None,
    requested_volume: float | None = None,
    requested_stop_loss: float | None = None,
    requested_take_profit: float | None = None,
) -> dict | None:
    """
    Sizes, prices, and sends a market order with SL/TP attached. Returns the
    MT5 order result as a dict on success, None on failure (never raises for
    a rejected order — trading loops should keep running after one bad fill).
    """
    require_mt5_runtime()
    ensure_connected()

    control = control_state()
    if control["status"] != "RUNNING" or not control["entriesAllowed"]:
        logger.info(
            "Skipping %s %s: runtime control=%s entriesAllowed=%s",
            symbol,
            direction.value,
            control["status"],
            control["entriesAllowed"],
        )
        return None

    if _apply_host_kill_switch():
        return None

    if check_daily_loss_guard():
        logger.info("Skipping %s %s: daily loss guard active.", symbol, direction.value)
        return None
    if check_max_drawdown_guard():
        logger.info("Skipping %s %s: peak drawdown guard active.", symbol, direction.value)
        return None
    if check_weekly_loss_guard():
        logger.info("Skipping %s %s: weekly loss guard active.", symbol, direction.value)
        return None
    if check_max_trades_guard():
        logger.info("Skipping %s %s: daily trade limit reached (%d).", symbol, direction.value, RISK.max_trades_per_day)
        return None

    # Keep the cap global across this bot's symbols, matching the configured risk limit.
    open_positions = get_open_positions(magic=RISK.magic_number)
    pending_orders = list(mt5.orders_get() or [])
    managed_pending = [order for order in pending_orders if getattr(order, "magic", RISK.magic_number) == RISK.magic_number]
    account_positions = get_open_positions()
    exposure_count = len(open_positions) + len(managed_pending)
    if exposure_count >= RISK.max_concurrent_positions:
        logger.info(
            "Skipping %s %s: max concurrent exposure reached (%d/%d; positions=%d pending=%d)",
            symbol, direction.value, exposure_count, RISK.max_concurrent_positions,
            len(open_positions), len(managed_pending),
        )
        return None
    if is_correlated_exposure_blocked(symbol, direction, open_positions):
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("symbol_info_tick returned None for %s — cannot price order.", symbol)
        return None

    entry_price = tick.ask if direction == TradeDirection.BUY else tick.bid
    if entry_price <= 0:
        logger.error("Invalid tick price %.5f for %s — skipping.", entry_price, symbol)
        return None
    sym = _get_symbol(symbol)
    spread_points = (float(tick.ask) - float(tick.bid)) / float(sym.info.point)
    if spread_points > RISK.max_spread_points:
        logger.warning(
            "Skipping %s %s: spread %.1f points exceeds configured cap %.1f",
            symbol, direction.value, spread_points, RISK.max_spread_points,
        )
        return None

    try:
        if not math.isfinite(atr) or atr <= 0:
            raise OrderError("ATR must be finite and positive for bounded stop calculation")
        if requested_stop_loss is None or requested_take_profit is None:
            sl, tp = calculate_sl_tp(symbol, direction, entry_price, atr)
        else:
            sl, tp = float(requested_stop_loss), float(requested_take_profit)
            if direction == TradeDirection.BUY and not (sl < entry_price < tp):
                raise OrderError("BUY proposal must have stop_loss < entry < take_profit")
            if direction == TradeDirection.SELL and not (tp < entry_price < sl):
                raise OrderError("SELL proposal must have take_profit < entry < stop_loss")
            sl_mode, tp_mode = ("down", "up") if direction == TradeDirection.BUY else ("up", "down")
            sl = _snap_price(sl, sym.tick_size, sl_mode, sym.info.digits)
            tp = _snap_price(tp, sym.tick_size, tp_mode, sym.info.digits)
        sl_distance = abs(entry_price - sl)
        tp_distance = abs(tp - entry_price)
        maximum_stop_distance = max(atr * RISK.max_stop_atr_multiplier, sym.min_stop_points)
        reward_risk = tp_distance / sl_distance if sl_distance > 0 else 0.0
        if sl_distance <= 0 or sl_distance > maximum_stop_distance:
            raise OrderError(
                f"Stop distance {sl_distance:.8f} exceeds bounded maximum {maximum_stop_distance:.8f}"
            )
        if not RISK.min_reward_risk_ratio <= reward_risk <= RISK.max_reward_risk_ratio:
            raise OrderError(
                f"Reward/risk ratio {reward_risk:.2f} is outside configured bounds "
                f"[{RISK.min_reward_risk_ratio:.2f}, {RISK.max_reward_risk_ratio:.2f}]"
            )
        max_risk_lots = calculate_lot_size(symbol, sl_distance, direction)
        lots = requested_volume if requested_volume is not None else max_risk_lots
        if requested_volume is not None and requested_volume > max_risk_lots:
            raise OrderError(
                f"AI volume {requested_volume} exceeds risk-capped volume {max_risk_lots}"
            )
        if lots < sym.info.volume_min or lots > sym.info.volume_max:
            raise OrderError(f"AI volume {lots} is outside broker bounds for {symbol}")
        # Always round down: an AI-proposed volume must never be rounded into
        # a larger-than-approved risk exposure.
        lots = math.floor(lots / sym.step) * sym.step
        lots = round(lots, sym.step_decimals)
    except OrderError as e:
        logger.error("Pre-trade calculation failed for %s: %s", symbol, e)
        return None

    if lots <= 0:
        logger.warning(
            "Computed lot size is 0 for %s — skipping trade (risk too small vs. min lot).", symbol
        )
        return None

    try:
        total_open_risk = _managed_open_risk(account_positions, pending_orders)
    except OrderError as exc:
        logger.error("Aggregate-risk check blocked %s: %s", symbol, exc)
        return None
    account_equity = get_account_equity()
    proposed_risk = abs(entry_price - sl) / sym.tick_size * sym.tick_value * lots
    aggregate_limit = account_equity * RISK.max_aggregate_risk_pct / 100.0
    if total_open_risk + proposed_risk > aggregate_limit:
        logger.warning(
            "Skipping %s %s: aggregate stop risk %.2f + proposed %.2f exceeds cap %.2f",
            symbol, direction.value, total_open_risk, proposed_risk, aggregate_limit,
        )
        return None

    try:
        from data_provider import validate_symbol_trade_constraints

        validate_symbol_trade_constraints(symbol, entry_price, sl, tp)
    except Exception as exc:  # noqa: BLE001 - pragma: no cover - live MT5 broker guard
        logger.warning("Broker validation blocked %s %s: %s", symbol, direction.value, exc)
        return None

    order_type = mt5.ORDER_TYPE_BUY if direction == TradeDirection.BUY else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp,
        "deviation": max(int(RISK.deviation_points), 20),  # broker-safe minimum tolerance
        "magic": RISK.magic_number,
        "comment": "ai-proposal-bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # Broker-side preflight catches account/symbol constraints which can only
    # be known by the trade server at this instant. A successful check still
    # does not replace the retcode validation after order_send.
    check = mt5.order_check(request)
    acceptable_check_codes = {0, getattr(mt5, "TRADE_RETCODE_DONE", 0)}
    if check is None or getattr(check, "retcode", None) not in acceptable_check_codes:
        reason = getattr(check, "comment", "") or str(mt5.last_error())
        logger.error(
            "Broker order_check rejected %s %s: %s",
            symbol, direction.value, reason,
        )
        add_log("ERROR", f"Order rejected: {reason}")
        return None

    if not EXECUTION.live_orders_enabled:
        logger.warning(
            "PAPER MODE: order_send suppressed for %s %s. Request details omitted from ledger.",
            symbol, direction.value,
        )
        return {"paper": True, "request": request}

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send returned None for %s: %s", symbol, mt5.last_error())
        return None

    if result.retcode == getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1):
        reason = (
            f"Partial fill for {symbol} {direction.value}; broker reconciliation required "
            f"(order={result.order}, filled={result.volume})"
        )
        logger.critical(reason)
        add_log("ERROR", reason)
        set_control("PAUSED", reason=reason, source="PARTIAL_FILL_RECOVERY")
        _record_fill_risk_or_halt(result, symbol, sl_distance)
        _record_filled_trade()
        partial_result = result._asdict()
        partial_result["partial_fill"] = True
        return partial_result

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        code_name = _retcode_to_text(result.retcode)
        logger.error(
            "Order rejected for %s %s: retcode=%s (%s) comment=%s",
            symbol,
            direction.value,
            result.retcode,
            code_name,
            result.comment,
        )
        add_log("ERROR", f"Order rejected: {result.comment or code_name}")
        ORDERS_PLACED.labels(
            symbol=symbol, direction=direction.value, result="rejected"
        ).inc()
        if result.retcode in {
            mt5.TRADE_RETCODE_REQUOTE,
            mt5.TRADE_RETCODE_PRICE_CHANGED,
            mt5.TRADE_RETCODE_OFF_QUOTES,
            mt5.TRADE_RETCODE_TIMEOUT,
            mt5.TRADE_RETCODE_CONNECTION,
            mt5.TRADE_RETCODE_BUSY,
        }:
            logger.warning(
                "Broker returned a transient execution error for %s; order skipped.", symbol
            )
        return None

    # --- Post-fill slippage verification ---
    fill_price = float(result.price or entry_price)
    slippage = abs(fill_price - entry_price)
    max_slippage = RISK.deviation_points * _get_symbol(symbol).info.point
    if slippage > max_slippage:
        logger.warning(
            "Slippage %.5f exceeds tolerance %.5f on %s (fill=%.5f expected=%.5f)",
            slippage,
            max_slippage,
            symbol,
            fill_price,
            entry_price,
        )
        reason = f"Fill slippage {slippage:.8f} exceeded tolerance {max_slippage:.8f} on {symbol}"
        add_log("ERROR", reason)
        set_control("PAUSED", reason=reason, source="SLIPPAGE_GUARD")

    logger.info(
        "Order filled: %s %s %.2f lots @ %.5f | SL=%.5f TP=%.5f | ticket=%s | slippage=%.5f",
        symbol,
        direction.value,
        lots,
        fill_price,
        sl,
        tp,
        result.order,
        slippage,
    )
    _record_fill_risk_or_halt(result, symbol, sl_distance)
    _record_filled_trade()
    audit_record = {
        "ticket": int(result.order or 0),
        "symbol": symbol,
        "direction": direction.value,
        "fill_price": fill_price,
        "volume": lots,
        "sl": sl,
        "tp": tp,
        "atr": atr,
        "reason": signal_reason or "not supplied",
        **(audit_context or {}),
    }
    logger.info("TRADE_AUDIT %s", json.dumps(audit_record, sort_keys=True, default=str))
    ORDERS_PLACED.labels(
        symbol=symbol, direction=direction.value, result="filled"
    ).inc()
    return result._asdict()


# ---------------------------------------------------------------------------
# Trailing stop management
# ---------------------------------------------------------------------------
@mt5_serialized
def manage_trailing_stops(symbol: str | None = None) -> None:
    """
    For every open position opened by this bot (matched by magic number):
    once floating profit reaches RISK.trailing_trigger_rr multiples of the
    original SL distance, move the stop to lock in profit and trail it by
    RISK.trailing_atr_multiplier * ATR behind price from then on.

    Call this once per loop iteration from main.py.
    """
    if not EXECUTION.live_orders_enabled:
        logger.debug("Skipping trailing-stop updates in paper mode")
        return
    control = control_state()
    if not control.get("managementAllowed", False):
        logger.info("Skipping trailing-stop updates: runtime control=%s", control.get("status", "HALTED"))
        return

    require_mt5_runtime()
    ensure_connected()
    positions = get_open_positions(symbol=symbol, magic=RISK.magic_number)
    if symbol is None:
        open_identifiers = {int(getattr(p, "identifier", p.ticket)) for p in positions}
        stale = set(_original_risk_by_position) - open_identifiers
        for position_id in stale:
            with _position_state_lock:
                _original_risk_by_position.pop(position_id, None)
        if stale:
            _save_position_state()
    if not positions:
        return  # fast-path: nothing to manage

    # Pre-fetch cached symbol info once per distinct symbol (not per position)
    sym_map: dict[str, _SymbolData] = {}
    for pos in positions:
        if pos.symbol not in sym_map:
            try:
                sym_map[pos.symbol] = _get_symbol(pos.symbol)
            except OrderError:
                logger.warning("Skipping trailing for %s: symbol info unavailable.", pos.symbol)

    for pos in positions:
        sym = sym_map.get(pos.symbol)
        if sym is None:
            continue

        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            logger.warning("Skipping trailing check for %s: missing tick info.", pos.symbol)
            continue

        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        current_price = tick.bid if is_buy else tick.ask

        fallback = abs(pos.price_open - pos.sl) if pos.sl else 0.0
        original_risk = _get_original_risk(int(getattr(pos, "identifier", pos.ticket)), fallback)
        if not original_risk or original_risk <= 0:
            continue

        current_profit_distance = (
            (current_price - pos.price_open) if is_buy else (pos.price_open - current_price)
        )
        rr_multiple = current_profit_distance / original_risk

        if rr_multiple < RISK.trailing_trigger_rr:
            continue  # not yet at 1:1, leave SL alone

        atr_estimate = original_risk / RISK.atr_sl_multiplier
        trail_distance = atr_estimate * RISK.trailing_atr_multiplier

        if is_buy:
            new_sl = _snap_price(current_price - trail_distance, sym.tick_size, "down", sym.info.digits)
            should_update = new_sl > pos.sl
        else:
            new_sl = _snap_price(current_price + trail_distance, sym.tick_size, "up", sym.info.digits)
            should_update = new_sl < pos.sl

        if not should_update:
            continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.tp,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "Trailing SL update failed for ticket %s: %s",
                pos.ticket,
                result.comment if result else mt5.last_error(),
            )
        else:
            logger.info(
                "Trailed SL for ticket %s (%s): %.5f -> %.5f (RR=%.2f)",
                pos.ticket,
                pos.symbol,
                pos.sl,
                new_sl,
                rr_multiple,
            )
