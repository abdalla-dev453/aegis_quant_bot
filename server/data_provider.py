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
import time
from dataclasses import dataclass 

import pandas as pd


try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise ImportError(
        "The MetaTrader5 package is only available on Windows with a "
       "local MT5 terminal installed. Install it with "
       "`pip install MetaTrader5` on a Windows host."
   ) from exc

from config import CREDENTIALS, TRADING_SYMBOLS

logger = logging.getLogger(
    "trading_bot.data_provider"
)

TIMEFRAME_MAP: dict[str, int] = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

class MT5ConnectionError(RuntimeError):
    """Raised when the terminal cannot be initialized or is unresponsive."""

@dataclass
class ConnectionState:
    conncted: bool = False
    last_error: str | None = None

_state = ConnectionState()


def initialize_connection(max_retries: int = 3, retry_delay_s: float = 5.0) -> None:
    """
    Initialize and log in to the MT5 terminal. Retries transient failures
    (terminal still starting, brief network blip) before giving up.

    Raises:
        MT5ConnectionError: if all retries are exhausted.
    """
    for attempt in range(1, max_retries + 1):
        kwargs = {}
        if CREDENTIALS.terminal_path:
            kwargs["path"] = CREDENTIALS.terminal_path

        ok = mt5.initialize(
            login=CREDENTIALS.login or None,
            password=CREDENTIALS.password or None,
            server=CREDENTIALS.server or None,
            timeout=CREDENTIALS.timeout_ms,
            **kwargs,
        )

        if ok:
            account_info = mt5.account_info()
            if account_info is None:
                err = mt5.last_error()
                logger.warning(
                    "initialize() succeeded but account_info() returned None "
                    "(attempt %d/%d): %s", attempt, max_retries, err
                )
            else:
                _state.connected = True
                _state.last_error = None
                logger.info(
                    "Connected to MT5. Account #%s | Balance: %.2f %s | Server: %s",
                    account_info.login, account_info.balance,
                    account_info.currency, account_info.server,
                )
                return

        err = mt5.last_error()
        _state.last_error = str(err)
        logger.error(
            "MT5 initialize() failed (attempt %d/%d): %s", attempt, max_retries, err
        )
        mt5.shutdown()
        time.sleep(retry_delay_s)

    raise MT5ConnectionError(
        f"Could not connect to MT5 terminal after {max_retries} attempts. "
        f"Last error: {_state.last_error}"
    )


def ensure_connected() -> None:
    """
    Cheap liveness check used before every trading action. Reconnects once
    if the terminal has dropped (e.g. terminal restarted, network hiccup).
    """
    if not mt5.terminal_info():
        logger.warning("MT5 terminal_info() unavailable — connection appears lost. Reconnecting...")
        _state.connected = False
        initialize_connection()


def shutdown_connection() -> None:
    if _state.connected:
        mt5.shutdown()
        _state.connected = False
        logger.info("MT5 connection shut down cleanly.")


def validate_symbols() -> None:
    """Confirm every configured symbol exists and is visible in Market Watch."""
    for sym_cfg in TRADING_SYMBOLS:
        info = mt5.symbol_info(sym_cfg.name)
        if info is None:
            raise MT5ConnectionError(f"Symbol '{sym_cfg.name}' not found on this broker/server.")
        if not info.visible:
            if not mt5.symbol_select(sym_cfg.name, True):
                raise MT5ConnectionError(f"Could not add '{sym_cfg.name}' to Market Watch.")
            logger.info("Symbol %s added to Market Watch.", sym_cfg.name)


def get_rates(symbol: str, timeframe_key: str, n_bars: int) -> pd.DataFrame:
    """
    Fetch the last `n_bars` completed candles for `symbol` on `timeframe_key`
    (e.g. "H1", "H4") and return a clean, indexed DataFrame.

    Note: mt5.copy_rates_from_pos(..., start_pos=1, ...) is used (not 0) so
    we always work with fully closed candles, never the currently forming one.
    """
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
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df[["open", "high", "low", "close", "volume", "spread"]]


def get_latest_closed_candle_time(symbol: str, timeframe_key: str) -> pd.Timestamp:
    """Used by main.py's loop to detect when a new candle has closed."""
    df = get_rates(symbol, timeframe_key, n_bars=1)
    return df.index[-1]


def get_account_equity() -> float:
    ensure_connected()
    info = mt5.account_info()
    if info is None:
        raise MT5ConnectionError(f"account_info() failed: {mt5.last_error()}")
    return float(info.equity)


def get_symbol_info(symbol: str):
    ensure_connected()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5ConnectionError(f"symbol_info() failed for {symbol}: {mt5.last_error()}")
    return info


def get_open_positions(symbol: str | None = None, magic: int | None = None) -> list:
    ensure_connected()
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        return []
    if magic is not None:
        positions = [p for p in positions if p.magic == magic]
    return list(positions)
