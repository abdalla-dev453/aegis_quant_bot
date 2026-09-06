"""
main.py
-------
Asynchronous execution loop. Runs continuously, polling for newly closed
H1 candles per symbol and only re-evaluating a symbol's signal once its
candle has actually closed (never mid-candle, which would repaint).

Usage:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import threading

import pandas as pd

from config import (
    CANDLES_TO_FETCH,
    LOGGING,
    RISK,
    STRATEGY,
    TIMEFRAME_BIAS,
    TIMEFRAME_TRIGGER,
    TRADING_SYMBOLS,
    MAX_BACKOFF_SECONDS,
    INITIAL_BACKOFF_SECONDS,
)
from data_provider import (
    MT5ConnectionError,
    get_rates,
    initialize_connection,
    mt5,
    shutdown_connection,
    resolve_and_validate_symbols,
    resolved_symbol,
)
from execution import place_order, manage_trailing_stops
from strategy import TradeDirection, compute_indicators, generate_signal
from runtime_state import add_log, update

logger = logging.getLogger("trading_bot.main")


def start_dashboard_api() -> None:
    try:
        import uvicorn
        from api import app

        api_thread = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={
                "host": os.getenv("API_HOST", "127.0.0.1"),
                "port": int(os.getenv("API_PORT", "8000")),
                "log_level": "warning",
            },
            daemon=True,
        )
        api_thread.start()
        logger.info("Dashboard API listening on http://127.0.0.1:8000")
    except Exception:
        logger.exception("Dashboard API failed to start; trading loop will continue.")


def setup_logging() -> None:
    level = getattr(logging, LOGGING.level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    root = logging.getLogger("trading_bot")
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOGGING.log_file, maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)


class LastCandleTracker:
    """Tracks the last-seen closed candle timestamp per symbol to avoid
    re-evaluating the same H1 candle repeatedly while we wait for the next
    one to close."""

    def __init__(self) -> None:
        self._last_seen: dict[str, pd.Timestamp] = {}

    def is_new_candle(self, symbol: str, candle_time: pd.Timestamp) -> bool:
        prev = self._last_seen.get(symbol)
        return prev is None or candle_time > prev

    def mark_seen(self, symbol: str, candle_time: pd.Timestamp) -> None:
        self._last_seen[symbol] = candle_time


async def evaluate_symbol(symbol: str, tracker: LastCandleTracker) -> None:
    """Fetch data, check for a new closed H1 candle, and act on a fresh signal."""
    try:
        # Fetch H1 and H4 concurrently — the two calls are independent and
        # each spends most of its time blocked on the MT5 IPC call.
        df_h1_raw, df_h4_raw = await asyncio.gather(
            asyncio.to_thread(get_rates, symbol, TIMEFRAME_TRIGGER, CANDLES_TO_FETCH),
            asyncio.to_thread(get_rates, symbol, TIMEFRAME_BIAS, CANDLES_TO_FETCH),
        )

        # NaN/NaT guard: a garbage timestamp must not corrupt the tracker
        latest_candle_time = pd.Timestamp(df_h1_raw.index[-1])
        if pd.isna(latest_candle_time):
            logger.warning("%s: latest candle timestamp is NaT — skipping cycle.", symbol)
            return

        if not tracker.is_new_candle(symbol, latest_candle_time):
            return  # already evaluated this candle; nothing to do yet

        df_h1, df_h4 = await asyncio.gather(
            asyncio.to_thread(compute_indicators, df_h1_raw),
            asyncio.to_thread(compute_indicators, df_h4_raw),
        )

        if df_h1.empty or df_h4.empty:
            logger.warning("%s: not enough warmed-up candle data yet, skipping.", symbol)
            tracker.mark_seen(symbol, latest_candle_time)
            return

        signal = await asyncio.to_thread(generate_signal, symbol, df_h1, df_h4)
        tracker.mark_seen(symbol, latest_candle_time)

        logger.info(
            "%s | candle=%s | trend=%s | sentiment=%+.2f | signal=%s | reason=%s",
            symbol,
            latest_candle_time,
            signal.technical_trend.value,
            signal.sentiment_score,
            signal.direction.value,
            signal.reason,
        )
        technical = (
            1.0
            if signal.technical_trend.value == "bullish"
            else -1.0 if signal.technical_trend.value == "bearish" else 0.0
        )
        update(
            last_signal={
                "composite": technical,
                "label": signal.technical_trend.value.upper(),
                "technical": technical,
                "sentiment": signal.sentiment_score,
                "momentum": technical if signal.direction != TradeDirection.NONE else 0.0,
            }
        )
        add_log("INFO", f"{symbol} {signal.direction.value}: {signal.reason}")

        if signal.direction in (TradeDirection.BUY, TradeDirection.SELL):
            await asyncio.to_thread(place_order, symbol, signal.direction, signal.atr)

    except MT5ConnectionError as e:
        logger.error("%s: connection error during evaluation: %s", symbol, e)
    except Exception:
        logger.exception("%s: unexpected error during evaluation", symbol)


class ErrorBackoff:
    """Circuit-breaker-ish backoff: on consecutive failures, progressively
    delay the loop so a dead feed doesn't spin at full polling rate."""

    def __init__(self) -> None:
        self._consecutive = 0

    def record_success(self) -> None:
        self._consecutive = 0

    def record_failure(self) -> float:
        self._consecutive += 1
        return min(
            INITIAL_BACKOFF_SECONDS * (2 ** min(self._consecutive - 1, 6)),
            MAX_BACKOFF_SECONDS,
        )


async def trading_loop(stop_event: asyncio.Event) -> None:
    tracker = LastCandleTracker()
    backoff = ErrorBackoff()

    while not stop_event.is_set():
        if mt5 is None:
            await stop_event.wait()
            continue

        had_error = False
        if not stop_event.is_set():
            results = await asyncio.gather(
                *(
                    evaluate_symbol(resolved_symbol(sym_cfg.name), tracker)
                    for sym_cfg in TRADING_SYMBOLS
                ),
                return_exceptions=True,
            )
            for sym_cfg, result in zip(TRADING_SYMBOLS, results):
                if isinstance(result, MT5ConnectionError):
                    had_error = True
                    logger.error("%s: connection error: %s", sym_cfg.name, result)
                elif isinstance(result, Exception):
                    had_error = True
                    logger.exception("%s: unexpected error in loop", sym_cfg.name, exc_info=result)
                else:
                    backoff.record_success()

        try:
            await asyncio.to_thread(manage_trailing_stops)
        except MT5ConnectionError as e:
            logger.error("Trailing stop management failed: %s", e)
        except Exception:
            logger.exception("Unexpected error while managing trailing stops")

        poll = STRATEGY.loop_poll_seconds
        if had_error:
            extra = backoff.record_failure()
            logger.warning("Loop errors — backing off an extra %.1fs.", extra)
            poll += extra

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll)
        except asyncio.TimeoutError:
            pass  # normal — just means it's time to poll again


async def main() -> None:
    setup_logging()
    logger.info(
        "Starting trading bot | symbols=%s | risk/trade=%.2f%%",
        [s.name for s in TRADING_SYMBOLS],
        RISK.risk_per_trade_pct,
    )

    start_dashboard_api()
    try:
        initialize_connection()
        resolve_and_validate_symbols()
        update(connected=True)
    except MT5ConnectionError:
        logger.error(
            "MT5 unavailable at startup; enter credentials in the dashboard Settings page."
        )

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig_name):
            try:
                loop.add_signal_handler(getattr(signal, sig_name), stop_event.set)
            except NotImplementedError:
                # add_signal_handler isn't available on Windows for SIGTERM in
                # some Python versions — fall back to default handling there.
                pass

    try:
        await trading_loop(stop_event)
    finally:
        logger.info("Shutting down...")
        update(connected=False)
        shutdown_connection()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
