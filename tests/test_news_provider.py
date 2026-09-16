"""Live-news cleaning and failure handling without terminal/network access."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

import news_provider


def test_normalize_record_returns_exact_live_news_schema() -> None:
    item = news_provider._normalize_record(
        {
            "title": "US CPI <b>inflation</b> report",
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "currency": "USD",
            "description": "Latest <i>market-moving</i> release",
        },
        "MT5_Terminal",
    )

    assert item == {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "source": "MT5_Terminal",
        "title": "US CPI inflation report",
        "impact_level": "HIGH",
        "currency_affected": "USD",
        "summary": "Latest market-moving release",
    }


def test_all_feed_failures_return_explicit_warning(monkeypatch) -> None:
    monkeypatch.setattr(news_provider, "_cache", None)
    monkeypatch.setattr(news_provider, "_terminal_news", lambda *_args: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(news_provider, "_newsapi", lambda: [])
    monkeypatch.setattr(news_provider, "_yahoo_rss", lambda: (_ for _ in ()).throw(requests.Timeout("down")))

    result = news_provider.get_latest_high_impact_news()

    assert result.items == []
    assert result.warning == "Warning: Live sentiment feed currently unavailable"
