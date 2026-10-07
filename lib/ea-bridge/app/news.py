"""
Macroeconomic News Calendar & Blackout Filter Service.

Protects trading operations during high-impact economic events (NFP, CPI, FOMC, Rate Decisions)
to avoid severe slippage, spread widening, and whipsaws.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field


class NewsEvent(BaseModel):
    id: str
    title: str
    currency: str
    impact: str = Field(description="HIGH | MEDIUM | LOW")
    scheduled_at: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class NewsHeadline(BaseModel):
    id: str
    title: str
    source: str
    impact: str = Field(default="MEDIUM", description="HIGH | MEDIUM | LOW")
    timestamp: datetime
    sentiment_score: float = Field(ge=-1.0, le=1.0, description="-1.0 (strongly bearish) to +1.0 (strongly bullish)")
    currencies: list[str] = Field(default_factory=list)


class SymbolSentimentResult(BaseModel):
    symbol: str
    overall_sentiment: str = Field(description="BULLISH | BEARISH | NEUTRAL")
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    headline_count: int
    headlines: list[NewsHeadline]
    trade_recommendation: str = Field(description="FAVOR_LONGS | FAVOR_SHORTS | STAND_DOWN | NEUTRAL")


class BlackoutStatus(BaseModel):
    is_blackout: bool
    symbol: str
    affected_currency: str | None = None
    event_title: str | None = None
    minutes_delta: float | None = None
    message: str


# Keyword sentiment dictionary for financial domain NLP
_BULLISH_KEYWORDS = {
    "rate hike": 0.8,
    "hawkish": 0.7,
    "inflation beat": 0.6,
    "gdp growth": 0.7,
    "jobs surge": 0.6,
    "record high": 0.5,
    "bullish": 0.6,
    "stronger than expected": 0.6,
    "expansion": 0.5,
    "tightening": 0.5,
    "surplus": 0.4,
    "rally": 0.5,
    "safe haven demand": 0.6,
}

_BEARISH_KEYWORDS = {
    "rate cut": -0.8,
    "dovish": -0.7,
    "recession": -0.8,
    "inflation miss": -0.5,
    "jobless claims rise": -0.6,
    "tariff": -0.5,
    "sanction": -0.5,
    "war": -0.7,
    "crisis": -0.8,
    "bearish": -0.6,
    "weaker than expected": -0.6,
    "contraction": -0.6,
    "easing": -0.5,
    "deficit": -0.4,
    "selloff": -0.6,
    "downgrade": -0.6,
}


def score_headline_sentiment(title: str) -> float:
    """Analyze text using financial keyword sentiment weights."""
    clean = title.lower()
    total_score = 0.0
    matched = 0

    for phrase, score in _BULLISH_KEYWORDS.items():
        if phrase in clean:
            total_score += score
            matched += 1

    for phrase, score in _BEARISH_KEYWORDS.items():
        if phrase in clean:
            total_score += score
            matched += 1

    if matched == 0:
        return 0.0

    # Bound within [-1.0, 1.0]
    avg_score = total_score / matched
    return max(-1.0, min(1.0, round(avg_score, 3)))


class MacroNewsService:
    """In-memory & pluggable macro calendar with blackout window & sentiment calculation."""

    def __init__(self) -> None:
        self._events: list[NewsEvent] = []
        self._headlines: list[NewsHeadline] = []
        self._seed_default_calendar()
        self._seed_default_headlines()

    def _seed_default_calendar(self) -> None:
        """Seed rolling high-impact calendar events relative to current week."""
        now = datetime.now(UTC)
        sample_titles = [
            ("USD", "Non-Farm Payrolls (NFP)"),
            ("USD", "Consumer Price Index (CPI) YoY"),
            ("USD", "FOMC Interest Rate Decision"),
            ("EUR", "ECB Main Refinancing Rate"),
            ("GBP", "BOE Monetary Policy Summary"),
            ("JPY", "BOJ Policy Rate & Statement"),
        ]
        for i, (curr, title) in enumerate(sample_titles):
            # Schedule events offset from today
            event_time = now.replace(minute=30, second=0, microsecond=0) + timedelta(days=(i % 5) + 1, hours=(i % 8) + 10)
            self._events.append(
                NewsEvent(
                    id=f"news-{curr.lower()}-{i + 1}",
                    title=title,
                    currency=curr,
                    impact="HIGH",
                    scheduled_at=event_time,
                    forecast="Expected",
                    previous="Prior",
                )
            )

    def _seed_default_headlines(self) -> None:
        """Seed initial real-time market headlines with NLP sentiment."""
        now = datetime.now(UTC)
        sample_feed = [
            ("US GDP growth accelerates to 3.0%, stronger than expected", "Reuters", "HIGH", ["USD"]),
            ("ECB signals potential rate cut as Eurozone inflation eases", "Bloomberg", "HIGH", ["EUR"]),
            ("BOJ reaffirms dovish stance, keeping borrowing costs near zero", "Nikkei", "MEDIUM", ["JPY"]),
            ("Gold hits new record high amid safe haven demand and geopolitical tensions", "FT", "HIGH", ["XAU", "USD"]),
            ("UK jobless claims rise sharply, raising stagflation fears", "Reuters", "MEDIUM", ["GBP"]),
        ]
        for i, (title, source, impact, currs) in enumerate(sample_feed):
            score = score_headline_sentiment(title)
            self._headlines.append(
                NewsHeadline(
                    id=f"hl-{i + 1}",
                    title=title,
                    source=source,
                    impact=impact,
                    timestamp=now - timedelta(minutes=(i + 1) * 20),
                    sentiment_score=score,
                    currencies=currs,
                )
            )

    def get_upcoming_events(self, horizon_hours: int = 48) -> list[NewsEvent]:
        """Return high-impact events within the next N hours."""
        now = datetime.now(UTC)
        horizon = now + timedelta(hours=horizon_hours)
        return [
            e for e in self._events
            if now - timedelta(hours=1) <= e.scheduled_at <= horizon
        ]

    def add_event(self, event: NewsEvent) -> None:
        self._events.append(event)

    def add_headline(self, headline: NewsHeadline) -> None:
        self._headlines.insert(0, headline)
        if len(self._headlines) > 200:
            self._headlines.pop()

    def get_recent_headlines(self, limit: int = 20) -> list[NewsHeadline]:
        return self._headlines[:limit]

    def analyze_symbol_sentiment(self, symbol: str) -> SymbolSentimentResult:
        """
        Analyze collective news sentiment for a given pair (e.g. EURUSD, XAUUSD).
        Considers base currency sentiment vs quote currency sentiment.
        """
        clean_sym = symbol.upper().replace("/", "").replace("_", "")
        base_curr = clean_sym[:3] if len(clean_sym) >= 3 else ""
        quote_curr = clean_sym[3:6] if len(clean_sym) >= 6 else ""

        relevant: list[NewsHeadline] = []
        base_scores: list[float] = []
        quote_scores: list[float] = []

        for h in self._headlines:
            is_base = base_curr in h.currencies
            is_quote = quote_curr in h.currencies
            if is_base or is_quote:
                relevant.append(h)
                weight = 1.0 if h.impact == "HIGH" else (0.6 if h.impact == "MEDIUM" else 0.3)
                if is_base:
                    base_scores.append(h.sentiment_score * weight)
                if is_quote:
                    quote_scores.append(h.sentiment_score * weight)

        # Base currency score minus quote currency score gives relative directional bias
        avg_base = sum(base_scores) / len(base_scores) if base_scores else 0.0
        avg_quote = sum(quote_scores) / len(quote_scores) if quote_scores else 0.0
        relative_score = avg_base - avg_quote

        # For commodities like Gold (XAUUSD):
        if base_curr == "XAU":
            # Gold sentiment is directly boosted by positive gold headlines or USD weakness
            relative_score = avg_base - (0.5 * avg_quote)

        relative_score = max(-1.0, min(1.0, round(relative_score, 3)))

        if relative_score >= 0.25:
            overall = "BULLISH"
            rec = "FAVOR_LONGS"
        elif relative_score <= -0.25:
            overall = "BEARISH"
            rec = "FAVOR_SHORTS"
        else:
            overall = "NEUTRAL"
            rec = "NEUTRAL"

        confidence = min(0.95, round(0.50 + abs(relative_score) * 0.45, 2)) if relevant else 0.50

        return SymbolSentimentResult(
            symbol=symbol.upper(),
            overall_sentiment=overall,
            sentiment_score=relative_score,
            confidence=confidence,
            headline_count=len(relevant),
            headlines=relevant[:10],
            trade_recommendation=rec,
        )

    def check_blackout(
        self,
        symbol: str,
        blackout_minutes_before: int = 30,
        blackout_minutes_after: int = 15,
        target_time: datetime | None = None,
    ) -> BlackoutStatus:
        """
        Check if trading is currently in a blackout window for a given symbol.
        Extracts base and quote currencies from symbol (e.g., 'EURUSD' -> 'EUR', 'USD').
        """
        clean_sym = symbol.upper().replace("/", "").replace("_", "")
        base_curr = clean_sym[:3] if len(clean_sym) >= 3 else ""
        quote_curr = clean_sym[3:6] if len(clean_sym) >= 6 else ""

        check_time = target_time or datetime.now(UTC)

        for event in self._events:
            if event.impact != "HIGH":
                continue
            if event.currency not in (base_curr, quote_curr):
                continue

            delta_sec = (event.scheduled_at - check_time).total_seconds()
            delta_min = delta_sec / 60.0

            # Inside blackout if:
            # - Event is upcoming within `blackout_minutes_before`
            # - Event just happened within `blackout_minutes_after`
            if -blackout_minutes_after <= delta_min <= blackout_minutes_before:
                return BlackoutStatus(
                    is_blackout=True,
                    symbol=symbol,
                    affected_currency=event.currency,
                    event_title=event.title,
                    minutes_delta=round(delta_min, 1),
                    message=(
                        f"Trading paused: '{event.title}' ({event.currency}) is "
                        f"{abs(round(delta_min, 1))} min {'away' if delta_min >= 0 else 'ago'}."
                    ),
                )

        return BlackoutStatus(
            is_blackout=False,
            symbol=symbol,
            message="No high-impact news blackout active for this symbol.",
        )


# Global singleton instance
macro_news_service = MacroNewsService()
