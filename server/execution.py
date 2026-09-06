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

import logging
import logging.handlers
import math
import threading
from collections import namedtuple
from queue import Queue, Empty
from typing import Any, Dict, Tuple, cast

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - Linux/test environment only.
    mt5 = cast(Any, None)

from config import RISK
from data_provider import (
    ensure_connected,
    get_account_equity,
    get_open_positions,
)
from strategy import TradeDirection

logger = logging.getLogger("trading_bot.execution")


def require_mt5_runtime() -> None:
    if mt5 is None:
        raise OrderError(
            "MetaTrader5 is not available in this runtime. This bot must run inside a "
            "Windows MT5 terminal with a live broker login."
        )


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
        except Exception:
            pass  # never block the hot path


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

_symbol_cache: Dict[str, _SymbolData] = {}
_cache_lock = threading.Lock()
_MAX_CACHE_SIZE = 128


def _get_symbol(symbol: str) -> _SymbolData:
    """Return cached symbol metadata; populate lazily on first access."""
    require_mt5_runtime()
    with _cache_lock:
        if symbol in _symbol_cache:
            return _symbol_cache[symbol]

    ensure_connected()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise OrderError(f"symbol_info returned None for {symbol}")

    tick_size = info.trade_tick_size or info.point
    tick_value = info.trade_tick_value
    step = info.volume_step or 0.01
    step_decimals = max(0, -int(math.floor(math.log10(step))))
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
        _symbol_cache[symbol] = sym
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


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------
def calculate_lot_size(symbol: str, sl_distance_price: float) -> float:
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

    # Snap to the broker's allowed volume step and clamp to min/max.
    lots = math.floor(raw_lots / sym.step) * sym.step
    lots = max(sym.info.volume_min, min(sym.info.volume_max, lots))
    lots = round(lots, sym.step_decimals)

    # --- Absolute guardrails ---
    if lots > MAX_SINGLE_ORDER_LOTS:
        raise OrderError(
            f"Computed lot size {lots} exceeds hard ceiling {MAX_SINGLE_ORDER_LOTS} for {symbol}"
        )

    # --- Negative margin protection: refuse trades that would over-lever ---
    account = mt5.account_info()
    if account is not None and account.margin_free is not None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None:
            approx_margin = (lots * sym.info.trade_contract_size * tick.ask) / max(
                account.leverage or 100, 1
            )
            if account.margin > 0 or approx_margin > 0:
                projected = ((account.margin or 0.0) + approx_margin) / account.equity * 100.0
                if account.equity > 0 and projected > MAX_MARGIN_UTILIZATION_PCT:
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
        sl = round(entry_price - sl_dist, sym.info.digits)
        tp = round(entry_price + tp_dist, sym.info.digits)
    elif direction == TradeDirection.SELL:
        sl = round(entry_price + sl_dist, sym.info.digits)
        tp = round(entry_price - tp_dist, sym.info.digits)
    else:
        raise OrderError("calculate_sl_tp called with TradeDirection.NONE")

    return sl, tp


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
#----------------------------------------------------------------
def place_order(symbol: str, direction: TradeDirection, atr: float) -> dict | None:
    """
    Sizes, prices, and sends a market order with SL/TP attached. Returns the
    MT5 order result as a dict on success, None on failure (never raises for
    a rejected order — trading loops should keep running after one bad fill).
    """
    require_mt5_runtime()
    ensure_connected()

    open_positions = get_open_positions(magic=RISK.magic_number)
    if len(open_positions) >= RISK.max_concurrent_positions:
        logger.info(
            "Skipping %s %s: max concurrent positions reached (%d/%d)",
            symbol,
            direction.value,
            len(open_positions),
            RISK.max_concurrent_positions,
        )
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("symbol_info_tick returned None for %s — cannot price order.", symbol)
        return None

    entry_price = tick.ask if direction == TradeDirection.BUY else tick.bid
    if entry_price <= 0:
        logger.error("Invalid tick price %.5f for %s — skipping.", entry_price, symbol)
        return None

    try:
        sl, tp = calculate_sl_tp(symbol, direction, entry_price, atr)
        sl_distance = abs(entry_price - sl)
        lots = calculate_lot_size(symbol, sl_distance)
    except OrderError as e:
        logger.error("Pre-trade calculation failed for %s: %s", symbol, e)
        return None

    if lots <= 0:
        logger.warning(
            "Computed lot size is 0 for %s — skipping trade (risk too small vs. min lot).", symbol
        )
        return None

    try:
        from data_provider import validate_symbol_trade_constraints

        validate_symbol_trade_constraints(symbol, entry_price, sl, tp)
    except Exception as exc:  # pragma: no cover - live MT5 broker guard
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
        "deviation": max(int(RISK.deviation_points), 20),
        "magic": RISK.magic_number,
        "comment": "confluence-bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send returned None for %s: %s", symbol, mt5.last_error())
        return None

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
    return result._asdict()


# ---------------------------------------------------------------------------
# Trailing stop management
# ---------------------------------------------------------------------------
def manage_trailing_stops(symbol: str | None = None) -> None:
    """
    For every open position opened by this bot (matched by magic number):
    once floating profit reaches RISK.trailing_trigger_rr multiples of the
    original SL distance, move the stop to lock in profit and trail it by
    RISK.trailing_atr_multiplier * ATR behind price from then on.

    Call this once per loop iteration from main.py.
    """
    require_mt5_runtime()
    ensure_connected()
    positions = get_open_positions(symbol=symbol, magic=RISK.magic_number)
    if not positions:
        return  # fast-path: nothing to manage

    # Pre-fetch cached symbol info once per distinct symbol (not per position)
    sym_map: Dict[str, _SymbolData] = {}
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

        # Original risk distance = |entry - original SL|. We don't have the
        # "original" SL stored separately once it's been trailed, so we use
        # the initial risk distance implied by entry vs current SL only on
        # the FIRST trail (before sl has moved away from its opening value
        # this still equals the original risk — a persistent per-ticket
        # store is recommended for production to track this exactly).
        original_risk = abs(pos.price_open - pos.sl) if pos.sl else None
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
            new_sl = round(current_price - trail_distance, sym.info.digits)
            should_update = new_sl > pos.sl
        else:
            new_sl = round(current_price + trail_distance, sym.info.digits)
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
