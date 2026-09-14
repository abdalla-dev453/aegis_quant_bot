"""Asynchronous, fail-closed GPT-4o proposal service for MT5 execution."""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from enum import Enum
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from config import AI

logger = logging.getLogger("trading_bot.ai")
_error_logger = logging.getLogger("trading_bot.ai.invalid_response")
_error_logger.setLevel(logging.ERROR)
_error_logger.propagate = False
if not _error_logger.handlers:
    handler = logging.handlers.RotatingFileHandler(
        Path(__file__).with_name("error.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _error_logger.addHandler(handler)


class ProposalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeProposal(BaseModel):
    """The only LLM output accepted by the order bridge."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False, strict=True
    )

    action: ProposalAction
    symbol: str = Field(min_length=1)
    volume: float = Field(ge=0.01)
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=2000)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @classmethod
    def hold(cls, symbol: str, reason: str) -> "TradeProposal":
        return cls(
            action=ProposalAction.HOLD,
            symbol=symbol,
            volume=0.01,
            confidence_score=0.0,
            reasoning=reason,
        )


SYSTEM_PROMPT = """You are a cautious FX and metals trading analyst. Return only one JSON object.
It must have exactly these fields: action (BUY, SELL, or HOLD), symbol, volume,
stop_loss, take_profit, confidence_score, and reasoning. Use HOLD whenever the
provided market data is insufficient or a protected stop cannot be justified.
Never invent prices, symbols, or data not supplied in the market context."""


# --- Connection pooling & circuit breaker ---
_client: AsyncOpenAI | None = None
_circuit_open = False
_circuit_failures = 0
_circuit_last_failure = 0.0
_CIRCUIT_THRESHOLD = 5
_CIRCUIT_RESET_SECONDS = 60


def _get_client() -> AsyncOpenAI:
    """Return singleton AsyncOpenAI client with connection pooling."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=AI.api_key,
            timeout=AI.timeout_seconds,
            max_retries=2,
        )
    return _client


def _check_circuit() -> bool:
    """Check if circuit breaker allows requests."""
    global _circuit_open, _circuit_failures, _circuit_last_failure
    if not _circuit_open:
        return True
    # Auto-reset after timeout
    if time.time() - _circuit_last_failure > _CIRCUIT_RESET_SECONDS:
        _circuit_open = False
        _circuit_failures = 0
        logger.warning("OpenAI circuit breaker reset after timeout")
        return True
    return False


def _record_success() -> None:
    global _circuit_failures
    _circuit_failures = 0


def _record_failure() -> None:
    global _circuit_failures, _circuit_open, _circuit_last_failure
    _circuit_failures += 1
    _circuit_last_failure = time.time()
    if _circuit_failures >= _CIRCUIT_THRESHOLD:
        _circuit_open = True
        logger.error("OpenAI circuit breaker OPENED after %d failures", _circuit_failures)


def validate_ai_configuration() -> None:
    """Fail startup before connecting to MT5 when secure AI configuration is absent."""
    AI.validate()


def _proposal_schema() -> dict[str, Any]:
    return TradeProposal.model_json_schema()


async def propose_trade(
    symbol: str, market_context: dict[str, Any], live_news: list[dict[str, str]], news_warning: str | None = None
) -> TradeProposal:
    """Request and validate an AI trade proposal; every failure becomes HOLD."""
    # Circuit breaker check
    if not _check_circuit():
        logger.warning("OpenAI circuit breaker open, failing closed to HOLD for %s", symbol)
        return TradeProposal.hold(symbol, "AI service circuit breaker open; fail-closed HOLD.")

    try:
        AI.validate()
        client = _get_client()
        response = await client.chat.completions.create(
            model=AI.model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{SYSTEM_PROMPT}\n\n--- LIVE MACROECONOMIC & MARKET NEWS CONTEXT ---\n"
                        f"{json.dumps(live_news, sort_keys=True)}\n"
                        f"{news_warning or ''}\n"
                        "Cross-reference these live macro/market drivers with technical trends. "
                        "Use HOLD when a high-volatility catalyst makes the setup unsafe."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "requested_symbol": symbol,
                            "trade_proposal_schema": _proposal_schema(),
                            "market_context": market_context,
                        },
                        sort_keys=True,
                    ),
                },
            ],
        )
        raw_response = response.choices[0].message.content or ""
        proposal = TradeProposal.model_validate_json(raw_response)
        if proposal.symbol != symbol.upper():
            raise ValueError(
                f"Proposal symbol {proposal.symbol} does not match requested {symbol.upper()}"
            )
        if proposal.action != ProposalAction.HOLD and (
            proposal.stop_loss is None or proposal.take_profit is None
        ):
            raise ValueError("BUY/SELL proposals require stop_loss and take_profit")
        _record_success()
        return proposal
    except (json.JSONDecodeError, ValidationError, ValueError, IndexError, AttributeError) as exc:
        # Raw model output is deliberately isolated from normal trading logs.
        _error_logger.error(
            "Invalid AI response for %s: %s | raw_len=%d", symbol, exc, len(locals().get("raw_response", ""))
        )
        _record_failure()
        return TradeProposal.hold(symbol, "AI response failed schema validation; fail-closed HOLD.")
    except Exception:
        logger.exception("AI request failed for %s; falling back to HOLD.", symbol)
        _record_failure()
        return TradeProposal.hold(symbol, "AI service unavailable; fail-closed HOLD.")
