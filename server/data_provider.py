"""
data_provider.py
-----------------
Owns the MT5 terminal connection lifecycle and all historical/live data
fetching. Nothing else in the codebase should call the `MetaTrader5`
module's connection functions directly — route everything through here so
reconnection logic lives in exactly one place.
"""

from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from functools import wraps
from threading import RLock
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - Linux/test environment only.
    mt5 = cast(Any, None)

from config import (
    CREDENTIALS,
    TRADING_SYMBOLS,
    MAX_RECONNECT_ATTEMPTS,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
)

logger = logging.getLogger("trading_bot.data_provider")


def require_mt5_runtime() -> None:
    if mt5 is None:
        raise MT5ConnectionError(
            "MetaTrader5 is not available in this runtime. This bot must run on a "
            "Windows machine with an MT5 terminal installed and a broker login."
        )


TIMEFRAME_MAP: dict[str, int] = {}
if mt5 is not None:
    TIMEFRAME_MAP = {
        "M1": getattr(mt5, "TIMEFRAME_M1", 0),
        "M5": getattr(mt5, "TIMEFRAME_M5", 0),
        "M15": getattr(mt5, "TIMEFRAME_M15", 0),
        "M30": getattr(mt5, "TIMEFRAME_M30", 0),
        "H1": getattr(mt5, "TIMEFRAME_H1", 0),
        "H4": getattr(mt5, "TIMEFRAME_H4", 0),
        "D1": getattr(mt5, "TIMEFRAME_D1", 0),
    }


class MT5ConnectionError(RuntimeError):
    """Raised when the terminal cannot be initialized or is unresponsive."""


@dataclass
class ConnectionState:
    connected: bool = False
    last_error: str | None = None


_state = ConnectionState()
_runtime_credentials: dict[str, Any] = {}
_mt5_lock = RLock()
_symbol_resolution: dict[str, str] = {}


@contextmanager
def mt5_operation_lock():
    """Serialize MT5 IPC and connection operations across worker/API threads."""
    with _mt5_lock:
        yield


def mt5_serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with _mt5_lock:
            return function(*args, **kwargs)

    return wrapper


def configure_runtime_credentials(
    login: int, password: str, server: str, terminal_path: str | None = None
) -> None:
    """Set session-only credentials supplied by the protected settings API."""
    with _mt5_lock:
        _runtime_credentials.clear()
        _runtime_credentials.update(
            login=login, password=password, server=server, terminal_path=terminal_path
        )


def _exponential_backoff_delay(attempt: int, base: float, max_delay: float) -> float:
    """Jittered exponential backoff: base * 2^(attempt-1) + random jitter."""
    delay = min(base * (2 ** (attempt - 1)), max_delay)
    return delay + random.uniform(0, delay * 0.1)


def initialize_connection(
    max_retries: int = MAX_RECONNECT_ATTEMPTS,
    initial_delay: float = INITIAL_BACKOFF_SECONDS,
) -> None:
    """
    Initialize and log in to the MT5 terminal using exponential backoff
    with jitter. Retries transient failures (terminal still starting, brief
    network blip) before giving up.

    Raises:
        MT5ConnectionError: if all retries are exhausted.
    """
    with _mt5_lock:
        _initialize_connection(max_retries, initial_delay)


def _initialize_connection(
    max_retries: int = MAX_RECONNECT_ATTEMPTS,
    initial_delay: float = INITIAL_BACKOFF_SECONDS,
) -> None:
    require_mt5_runtime()

    try:
        CREDENTIALS.validate_live_trade_config()
    except ValueError as exc:
        raise MT5ConnectionError(str(exc)) from exc

    for attempt in range(1, max_retries + 1):
        kwargs = {}
        login = _runtime_credentials.get("login", CREDENTIALS.login)
        password = _runtime_credentials.get("password", CREDENTIALS.password)
        server = _runtime_credentials.get("server", CREDENTIALS.server)
        terminal_path = _runtime_credentials.get("terminal_path", CREDENTIALS.terminal_path)
        if terminal_path:
            kwargs["path"] = terminal_path

        ok = mt5.initialize(
            login=login or None,
            password=password or None,
            server=server or None,
            timeout=CREDENTIALS.timeout_ms,
            **kwargs,
        )

        if ok:
            account_info = mt5.account_info()
            if account_info is None:
                err = mt5.last_error()
                logger.warning(
                    "initialize() succeeded but account_info() returned None "
                    "(attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    err,
                )
            else:
                _state.connected = True
                _state.last_error = None
                logger.info(
                    "Connected to MT5. Account #%s | Balance: %.2f %s | Server: %s",
                    account_info.login,
                    account_info.balance,
                    account_info.currency,
                    account_info.server,
                )
                return

        err = mt5.last_error()
        _state.last_error = str(err)
        logger.error(
            "MT5 initialize() failed (attempt %d/%d): %s",
            attempt,
            max_retries,
            err,
        )
        mt5.shutdown()

        if attempt < max_retries:
            delay = _exponential_backoff_delay(
                attempt,
                initial_delay,
                MAX_BACKOFF_SECONDS,
            )
            logger.info("Backing off for %.1fs before retry...", delay)
            time.sleep(delay)

    raise MT5ConnectionError(
        f"Could not connect to MT5 terminal after {max_retries} attempts. "
        f"Last error: {_state.last_error}"
    )


def ensure_connected() -> None:
    """
    Cheap liveness check used before every trading action. Reconnects once
    if the terminal has dropped (e.g. terminal restarted, network hiccup).
    """
    with _mt5_lock:
        require_mt5_runtime()
        info = mt5.terminal_info()
        if info is None:
            logger.warning(
                "MT5 terminal_info() returned None — connection appears lost. Reconnecting..."
            )
            _state.connected = False
            _initialize_connection()
            return

        if not _state.connected:
            logger.info("Connection alive but state unsynced — refreshing.")
            _state.connected = True


def shutdown_connection() -> None:
    with _mt5_lock:
        if _state.connected:
            mt5.shutdown()
            _state.connected = False
            logger.info("MT5 connection shut down cleanly.")


def _resolve_symbol_name(base_name: str) -> str | None:
    if mt5.symbol_info(base_name) is not None:
        return base_name
    for suffix in ["", ".a", ".pro", ".raw", "-ECN", "m", ".c"]:
        candidate = f"{base_name}{suffix}"
        if mt5.symbol_info(candidate) is not None:
            return candidate
    for symbol_info in mt5.symbols_get() or ():
        if symbol_info.name.upper().startswith(base_name.upper()):
            return symbol_info.name
    return None


@mt5_serialized
def resolve_and_validate_symbols() -> dict[str, str]:
    """Resolve configured symbols to broker names and make them visible."""
    require_mt5_runtime()
    resolved: dict[str, str] = {}
    for sym_cfg in TRADING_SYMBOLS:
        actual = _resolve_symbol_name(sym_cfg.name)
        if actual is None:
            raise MT5ConnectionError(
                f"Could not resolve '{sym_cfg.name}' under any suffix variant."
            )
        info = mt5.symbol_info(actual)
        if not info.visible:
            if not mt5.symbol_select(actual, True):
                raise MT5ConnectionError(f"Could not add '{actual}' to Market Watch.")
            logger.info("Symbol %s added to Market Watch.", actual)
        if actual != sym_cfg.name:
            logger.warning("Symbol '%s' resolved to broker name '%s'.", sym_cfg.name, actual)
        resolved[sym_cfg.name] = actual
    _symbol_resolution.update(resolved)
    return resolved


def resolved_symbol(base_name: str) -> str:
    return _symbol_resolution.get(base_name, base_name)


@mt5_serialized
def validate_symbol_trade_constraints(
    symbol: str, entry_price: float, sl: float, tp: float
) -> None:
    """Reject invalid broker limits before sending a server order."""
    require_mt5_runtime()
    ensure_connected()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5ConnectionError(f"symbol_info() failed for {symbol}: {mt5.last_error()}")

    if not info.trade_mode:
        raise MT5ConnectionError(f"Symbol '{symbol}' is not tradeable on this broker/server.")

    stop_level = int(getattr(info, "trade_stops_level", 0) or 0)
    freeze_level = int(getattr(info, "trade_freeze_level", 0) or 0)
    point = float(getattr(info, "point", 0.0) or 0.0)

    if stop_level > 0:
        min_distance = max(stop_level * point, 0.0)
        if abs(entry_price - sl) < min_distance or abs(tp - entry_price) < min_distance:
            raise MT5ConnectionError(
                f"Broker stop distance for {symbol} is below {min_distance} and was rejected."
            )

    if freeze_level > 0:
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and abs(tick.ask - tick.bid) > freeze_level * point:
            raise MT5ConnectionError(f"Symbol {symbol} exceeds broker freeze level; trade aborted.")

    if not (entry_price > 0 and sl > 0 and tp > 0):
        raise MT5ConnectionError(
            f"Invalid prices for {symbol}: entry={entry_price}, sl={sl}, tp={tp}"
        )


@mt5_serialized
def get_rates(symbol: str, timeframe_key: str, n_bars: int) -> pd.DataFrame:
    """
    Fetch the last `n_bars` completed candles for `symbol` on `timeframe_key`
    (e.g. "H1", "H4") and return a clean, indexed DataFrame.

    Note: mt5.copy_rates_from_pos(..., start_pos=1, ...) is used (not 0) so
    we always work with fully closed candles, never the currently forming one.

    Raises:
        MT5ConnectionError: on MT5-level failure (terminal down, bad symbol).
        ValueError: if the returned data is malformed (missing columns, all-NaN).
    """
    require_mt5_runtime()
    ensure_connected()

    tf = TIMEFRAME_MAP.get(timeframe_key)
    if tf is None:
        raise ValueError(f"Unsupported timeframe key: {timeframe_key}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 1, n_bars)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        raise MT5ConnectionError(
            f"copy_rates_from_pos returned no data for {symbol}/{timeframe_key}: {err}"
        )

    df = pd.DataFrame(rates)

    # --- Guard: validate required columns exist ---
    required_cols = {"time", "open", "high", "low", "close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"MT5 returned malformed data for {symbol}/{timeframe_key}: "
            f"missing columns {missing}"
        )

    # --- Guard: drop rows with NaN in essential OHLC columns ---
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise ValueError(
            f"All candle rows for {symbol}/{timeframe_key} contained NaN values — "
            "data is unusable."
        )

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True, errors="coerce")
    df = df.dropna(subset=["time"])  # remove any rows whose timestamp failed to coerce
    if df.empty:
        raise ValueError(f"All timestamps for {symbol}/{timeframe_key} are NaT/unparseable.")

    df.set_index("time", inplace=True)

    # --- Guard: ensure index is monotonic (no out-of-order candles) ---
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    # tick_volume may be absent on some instruments; default to 0
    if "tick_volume" in df.columns:
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
    else:
        df["volume"] = 0

    if "spread" not in df.columns:
        df["spread"] = 0.0

    return df.loc[:, ["open", "high", "low", "close", "volume", "spread"]].copy()


def get_latest_closed_candle_time(symbol: str, timeframe_key: str) -> pd.Timestamp:
    """Used by main.py's loop to detect when a new candle has closed."""
    df = get_rates(symbol, timeframe_key, n_bars=1)
    return pd.Timestamp(df.index[-1])


@mt5_serialized
def get_account_equity() -> float:
    require_mt5_runtime()
    ensure_connected()
    info = mt5.account_info()
    if info is None:
        raise MT5ConnectionError(f"account_info() failed: {mt5.last_error()}")
    return float(info.equity)


@mt5_serialized
def get_symbol_info(symbol: str):
    require_mt5_runtime()
    ensure_connected()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5ConnectionError(f"symbol_info() failed for {symbol}: {mt5.last_error()}")
    return info


@mt5_serialized
def get_open_positions(symbol: str | None = None, magic: int | None = None) -> list:
    require_mt5_runtime()
    ensure_connected()
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        return []
    if magic is not None:
        positions = [p for p in positions if getattr(p, "magic", None) == magic]
    return list(positions)
