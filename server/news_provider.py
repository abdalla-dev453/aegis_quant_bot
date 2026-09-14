"""Live macro-news ingestion with terminal-first, RSS-fallback resilience."""

from __future__ import annotations

import logging
import logging.handlers
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

import requests

from config import NEWS_CONFIG
from data_provider import ensure_connected, mt5, mt5_operation_lock

logger = logging.getLogger("trading_bot.news")
_error_logger = logging.getLogger("trading_bot.news.connection")
_error_logger.setLevel(logging.ERROR)
_error_logger.propagate = False
if not _error_logger.handlers:
    handler = logging.handlers.RotatingFileHandler(
        Path(__file__).with_name("news_error.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _error_logger.addHandler(handler)

_HIGH_IMPACT_TERMS = (
    "fomc", "fed", "interest rate", "rate decision", "non-farm", "nonfarm",
    "nfp", "cpi", "inflation", "gdp", "payroll", "employment", "ecb",
    "boe", "boj", "tariff", "sanction", "war", "emergency",
)
_MEDIUM_IMPACT_TERMS = ("pmi", "retail sales", "manufacturing", "bond", "yield")
_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "XAU")
_cache_lock = Lock()
_cache: tuple[float, "NewsFetchResult"] | None = None


@dataclass(frozen=True)
class NewsFetchResult:
    items: list[dict[str, str]]
    warning: str | None = None


def _clean(value: object, fallback: str = "") -> str:
    without_html = re.sub(r"<[^>]+>", " ", str(value or fallback))
    return re.sub(r"\s+", " ", without_html).strip()


def _as_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc)
            except (TypeError, ValueError):
                return None
    return None


def _impact(value: object, title: str) -> str:
    text = f"{value or ''} {title}".lower()
    if any(term in text for term in _HIGH_IMPACT_TERMS) or str(value).upper() in {"3", "HIGH"}:
        return "HIGH"
    if any(term in text for term in _MEDIUM_IMPACT_TERMS) or str(value).upper() in {"2", "MEDIUM"}:
        return "MEDIUM"
    return "LOW"


def _currency(value: object, title: str) -> str:
    explicit = _clean(value).upper()
    if explicit in _CURRENCIES:
        return explicit
    combined = f"{explicit} {title.upper()}"
    found = [currency for currency in _CURRENCIES if re.search(rf"\b{currency}\b", combined)]
    return found[0] if len(found) == 1 else "ALL"


def _record_to_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    if hasattr(record, "_asdict"):
        return record._asdict()
    return {name: getattr(record, name) for name in dir(record) if not name.startswith("_")}


def _normalize_record(record: Any, source: str) -> dict[str, str] | None:
    raw = _record_to_mapping(record)
    title = _clean(raw.get("title") or raw.get("name") or raw.get("event") or raw.get("headline"))
    timestamp = _as_utc(raw.get("timestamp") or raw.get("time") or raw.get("date") or raw.get("published"))
    if not title or timestamp is None:
        return None
    return {
        "timestamp": timestamp.isoformat(),
        "source": source,
        "title": title,
        "impact_level": _impact(raw.get("impact") or raw.get("importance"), title),
        "currency_affected": _currency(raw.get("currency"), title),
        "summary": _clean(raw.get("summary") or raw.get("description"), title),
    }


def _terminal_news(start: datetime, end: datetime) -> list[dict[str, str]]:
    """Read broker calendar/news only if the installed terminal bridge exposes it."""
    if mt5 is None:
        raise RuntimeError("MT5 terminal bridge is unavailable")
    with mt5_operation_lock():
        ensure_connected()
        for method_name in ("calendar_get", "news_get"):
            method = getattr(mt5, method_name, None)
            if not callable(method):
                continue
            try:
                records = method(start, end)
            except TypeError:
                records = method()
            if records is None:
                continue
            return [
                item for record in records if (item := _normalize_record(record, "MT5_Terminal")) is not None
            ]
    raise RuntimeError("Connected terminal does not expose calendar_get() or news_get()")


def _yahoo_rss() -> list[dict[str, str]]:
    response = requests.get(
        NEWS_CONFIG.yahoo_rss_url,
        headers={"User-Agent": "AegisQuant/1.0 (+market-news-ingestion)"},
        timeout=(3.0, NEWS_CONFIG.api_timeout_seconds),
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    records: list[dict[str, str]] = []
    for node in root.findall(".//item"):
        record = {
            "title": node.findtext("title"),
            "published": node.findtext("pubDate"),
            "description": node.findtext("description"),
        }
        normalized = _normalize_record(record, "Yahoo_Finance")
        if normalized is not None:
            records.append(normalized)
    return records


def _newsapi() -> list[dict[str, str]]:
    """Optional licensed/free-tier fallback, used only when a key is supplied."""
    if not NEWS_CONFIG.api_key:
        return []
    response = requests.get(
        NEWS_CONFIG.news_api_url,
        params={
            "q": "forex OR central bank OR inflation OR markets",
            "language": "en",
            "pageSize": 30,
            "apiKey": NEWS_CONFIG.api_key,
        },
        timeout=(3.0, NEWS_CONFIG.api_timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in (None, "ok"):
        raise ValueError(payload.get("message", "NewsAPI returned an error"))
    records = []
    for article in payload.get("articles", []):
        normalized = _normalize_record(
            {
                "title": article.get("title"),
                "published": article.get("publishedAt"),
                "description": article.get("description") or article.get("content"),
            },
            "NewsAPI",
        )
        if normalized is not None:
            records.append(normalized)
    return records


def _recent_unique(items: Iterable[dict[str, str]], start: datetime, limit: int) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    retained = []
    for item in items:
        timestamp = _as_utc(item["timestamp"])
        if timestamp is None or timestamp < start or item["impact_level"] != "HIGH":
            continue
        identity = (item["source"], item["title"])
        if identity not in seen:
            seen.add(identity)
            retained.append(item)
    return sorted(retained, key=lambda item: item["timestamp"], reverse=True)[:limit]


def get_latest_high_impact_news(limit: int = 10, hours: int = 24) -> NewsFetchResult:
    """Return latest high-impact drivers; errors degrade to an explicit warning."""
    global _cache
    now = datetime.now(timezone.utc)
    with _cache_lock:
        if _cache and time.monotonic() - _cache[0] < NEWS_CONFIG.cache_seconds:
            return _cache[1]

        start = now - timedelta(hours=hours)
        terminal_items: list[dict[str, str]] = []
        try:
            terminal_items = _terminal_news(start, now)
        except Exception as exc:
            _error_logger.error("MT5 terminal news retrieval failed: %s", exc)

        terminal_high = _recent_unique(terminal_items, start, limit)
        if terminal_high:
            result = NewsFetchResult(terminal_high)
        else:
            fallback_items: list[dict[str, str]] = []
            if NEWS_CONFIG.api_key:
                try:
                    fallback_items = _recent_unique(_newsapi(), start, limit)
                except (requests.RequestException, ValueError) as exc:
                    _error_logger.error("NewsAPI retrieval failed: %s", exc)
            try:
                if not fallback_items:
                    fallback_items = _recent_unique(_yahoo_rss(), start, limit)
                result = NewsFetchResult(fallback_items)
            except (requests.RequestException, ET.ParseError, ValueError) as exc:
                _error_logger.error("Yahoo Finance RSS retrieval failed: %s", exc)
                result = NewsFetchResult([], "Warning: Live sentiment feed currently unavailable")
        _cache = (time.monotonic(), result)
        return result
