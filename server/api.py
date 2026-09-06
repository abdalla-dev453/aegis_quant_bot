"""Read-only FastAPI bridge for the React monitoring dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import hmac
import os
from pathlib import Path
import time
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import CREDENTIALS, INDICATORS, NEWS_CONFIG, RISK, TRADING_SYMBOLS
from data_provider import (
    configure_runtime_credentials,
    ensure_connected,
    get_open_positions,
    get_rates,
    initialize_connection,
    mt5,
    mt5_operation_lock,
    shutdown_connection,
)
from runtime_state import read
from strategy import analyze_market_sentiment, compute_indicators

app = FastAPI(title="Aegis Quant API", version="1.0.0")
API_TOKEN = os.getenv("API_TOKEN", "")
_rate_lock = Lock()
_rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_MAX_RATE_KEYS = 10000


def require_api_token(x_api_key: str | None = Header(default=None)) -> None:
    if not API_TOKEN or not x_api_key or not hmac.compare_digest(x_api_key, API_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


def rate_limit(request: Request, bucket: str, limit: int, window_seconds: int = 60) -> None:
    now = time.monotonic()
    client = request.client.host if request.client else "unknown"
    key = (client, bucket)
    with _rate_lock:
        if len(_rate_windows) >= _MAX_RATE_KEYS and key not in _rate_windows:
            _rate_windows.clear()
        timestamps = _rate_windows[key]
        while timestamps and now - timestamps[0] >= window_seconds:
            timestamps.popleft()
        if len(timestamps) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        timestamps.append(now)


def read_limit(request: Request) -> None:
    rate_limit(request, "read", 120)


def credentials_limit(request: Request) -> None:
    rate_limit(request, "credentials", 3)


def protected(request: Request, _: None = Depends(require_api_token)) -> None:
    read_limit(request)


def protected_credentials(request: Request, _: None = Depends(require_api_token)) -> None:
    credentials_limit(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-API-Key"],
)

_calendar_cache: tuple[float, dict[str, Any]] | None = None
_credentials_configured = CREDENTIALS.is_configured()


class CredentialsPayload(BaseModel):
    login: int = Field(gt=0)
    password: str = Field(min_length=1)
    server: str = Field(min_length=1)
    terminal_path: str | None = None


def _account() -> Any:
    with mt5_operation_lock():
        ensure_connected()
        return mt5.account_info()


def _position_rows() -> list[dict[str, Any]]:
    with mt5_operation_lock():
        rows = []
        for pos in get_open_positions(magic=RISK.magic_number):
            rows.append(
                {
                    "ticket": str(pos.ticket),
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "lot": float(pos.volume),
                    "entry": float(pos.price_open),
                    "sl": float(pos.sl),
                    "tp": float(pos.tp),
                    "trailing": False,
                    "current": float(pos.price_current),
                    "pnl": float(pos.profit),
                    "digits": int(getattr(mt5.symbol_info(pos.symbol), "digits", 5)),
                }
            )
        return rows


def _history_deals(days: int = 90) -> list[Any]:
    with mt5_operation_lock():
        ensure_connected()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start = now - timedelta(days=days)
        deals = mt5.history_deals_get(start, now)
        if deals is None:
            return []
        return [
            deal
            for deal in deals
            if getattr(deal, "magic", None) == RISK.magic_number
            and getattr(deal, "entry", None) in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)
        ]


def _deal_net(deal: Any) -> float:
    return (
        float(getattr(deal, "profit", 0.0) or 0.0)
        + float(getattr(deal, "commission", 0.0) or 0.0)
        + float(getattr(deal, "swap", 0.0) or 0.0)
    )


@app.get("/api/health", dependencies=[Depends(protected)])
def health() -> dict[str, Any]:
    state = read()
    connected = bool(state["connected"])
    return {"ok": connected, "connected": connected, "service": "aegis-quant"}


@app.get("/api/settings", dependencies=[Depends(protected)])
def settings() -> dict[str, Any]:
    return {
        "credentialsConfigured": _credentials_configured,
        "symbols": [symbol.name for symbol in TRADING_SYMBOLS],
        "timeframeTrigger": "H1",
        "timeframeBias": "H4",
        "riskPerTradePct": RISK.risk_per_trade_pct,
        "atrStopMultiplier": RISK.atr_sl_multiplier,
        "atrTakeProfitMultiplier": RISK.atr_tp_multiplier,
        "maxConcurrentPositions": RISK.max_concurrent_positions,
        "magicNumber": RISK.magic_number,
    }


@app.post("/api/settings/credentials", dependencies=[Depends(protected_credentials)])
def save_credentials(payload: CredentialsPayload) -> dict[str, Any]:
    global _credentials_configured
    try:
        if payload.terminal_path:
            terminal = Path(payload.terminal_path).expanduser().resolve()
            if terminal.name.lower() != "terminal64.exe" or not terminal.is_file():
                raise ValueError("Invalid MT5 terminal path")
        with mt5_operation_lock():
            configure_runtime_credentials(
                payload.login, payload.password, payload.server, payload.terminal_path
            )
            shutdown_connection()
            initialize_connection()
        _credentials_configured = True
        return {"ok": True, "connected": True, "message": "MT5 connection established."}
    except Exception:
        _credentials_configured = False
        raise HTTPException(status_code=400, detail="MT5 connection failed")


@app.get("/api/account", dependencies=[Depends(protected)])
def account() -> dict[str, float]:
    info = _account()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    with mt5_operation_lock():
        deals = mt5.history_deals_get(day_start, now.replace(tzinfo=None)) or []
    realized_today = sum(
        _deal_net(deal) for deal in deals if getattr(deal, "magic", None) == RISK.magic_number
    )
    floating_today = sum(row["pnl"] for row in _position_rows())
    return {
        "netEquity": float(info.equity),
        "balance": float(info.balance),
        "todaysPnl": realized_today + floating_today,
        "freeMargin": float(info.margin_free),
        "marginLevel": float(info.margin_level or 0.0),
    }


@app.get("/api/positions", dependencies=[Depends(protected)])
def positions() -> list[dict[str, Any]]:
    return _position_rows()


@app.get("/api/risk", dependencies=[Depends(protected)])
def risk() -> dict[str, Any]:
    info = _account()
    margin = float(info.margin or 0.0)
    equity = float(info.equity or 0.0)
    today_pnl = account()["todaysPnl"]
    start_equity = equity - today_pnl
    drawdown = max(0.0, (start_equity - equity) / start_equity * 100.0) if start_equity > 0 else 0.0
    return {
        "drawdownPct": drawdown,
        "maxDrawdownCeilingPct": 3.0,
        "marginUtilizedPct": margin / equity * 100.0 if equity else 0.0,
        "openPositions": len(_position_rows()),
        "dailyVaR": 0.0,
        "riskPerTradePct": RISK.risk_per_trade_pct,
    }


@app.get("/api/confluence", dependencies=[Depends(protected)])
def confluence() -> dict[str, Any]:
    signal = read().get("last_signal", {})
    return {
        "composite": float(signal.get("composite", 0.0)),
        "label": str(signal.get("label", "NEUTRAL")),
        "technical": float(signal.get("technical", 0.0)),
        "sentiment": float(signal.get("sentiment", 0.0)),
        "momentum": float(signal.get("momentum", 0.0)),
    }


@app.get("/api/calendar", dependencies=[Depends(protected)])
def calendar() -> dict[str, Any]:
    global _calendar_cache
    now = time.monotonic()
    if _calendar_cache is None or now - _calendar_cache[0] >= 30.0:
        reading = analyze_market_sentiment(TRADING_SYMBOLS[0].name)
        event = (
            {
                "name": reading.next_high_impact_event,
                "currency": reading.next_event_currency or "",
                "impact": reading.next_event_impact,
                "timeUtc": reading.next_event_time_utc or "",
                "minutesAway": reading.minutes_to_next_event or 0.0,
            }
            if reading.next_high_impact_event
            else None
        )
        active = reading.minutes_to_next_event is not None and abs(
            reading.minutes_to_next_event
        ) <= max(NEWS_CONFIG.blackout_minutes_before, NEWS_CONFIG.blackout_minutes_after)
        payload = {
            "autoHaltActive": active,
            "autoHaltEtaSeconds": max(0, int((reading.minutes_to_next_event or 0) * 60)),
            "nextEvent": event,
        }
        _calendar_cache = (now, payload)
    return _calendar_cache[1]


@app.get("/api/performance", dependencies=[Depends(protected)])
def performance() -> dict[str, Any]:
    results = [_deal_net(deal) for deal in _history_deals()]
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "winRatePct": len(wins) / len(results) * 100.0 if results else 0.0,
        "profitFactor": gross_profit / gross_loss if gross_loss else 0.0,
        "totalTrades": len(results),
        "avgWin": sum(wins) / len(wins) if wins else 0.0,
        "avgLoss": sum(losses) / len(losses) if losses else 0.0,
    }


@app.get("/api/equity-curve", dependencies=[Depends(protected)])
def equity_curve() -> list[dict[str, Any]]:
    info = _account()
    deals = sorted(_history_deals(days=30), key=lambda deal: deal.time)
    if not deals:
        return [
            {"date": datetime.now(timezone.utc).date().isoformat(), "equity": float(info.equity)}
        ]
    current_equity = float(info.equity)
    daily: dict[str, float] = {}
    for deal in deals:
        date = datetime.fromtimestamp(deal.time, timezone.utc).date().isoformat()
        daily[date] = daily.get(date, 0.0) + _deal_net(deal)
    points = []
    running = current_equity - sum(daily.values())
    for date, pnl in sorted(daily.items()):
        running += pnl
        points.append({"date": date, "equity": running})
    return points


@app.get("/api/price-series", dependencies=[Depends(protected)])
def price_series() -> dict[str, Any]:
    symbol = TRADING_SYMBOLS[0].name
    frame = compute_indicators(get_rates(symbol, "H1", 120)).tail(100)
    points = [
        {
            "time": timestamp.isoformat(),
            "price": float(row.close),
            "ema50": float(row[f"ema_{INDICATORS.ema_fast}"]),
            "ema200": float(row[f"ema_{INDICATORS.ema_slow}"]),
        }
        for timestamp, row in frame.iterrows()
    ]
    return {
        "symbol": symbol,
        "points": points,
    }


@app.get("/api/logs", dependencies=[Depends(protected)])
def logs() -> list[dict[str, Any]]:
    return read().get("logs", [])
