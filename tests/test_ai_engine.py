"""Schema and fail-closed behavior for the AI proposal boundary."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

import ai_engine
from ai_engine import ProposalAction, TradeProposal


def test_trade_proposal_rejects_unknown_fields_and_invalid_confidence() -> None:
    with pytest.raises(Exception):
        TradeProposal.model_validate(
            {
                "action": "BUY",
                "symbol": "EURUSD",
                "volume": 0.01,
                "confidence_score": 1.1,
                "reasoning": "invalid confidence",
                "unexpected": True,
            }
        )


@pytest.mark.asyncio
async def test_invalid_ai_json_falls_back_to_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCompletions:
        async def create(self, **_kwargs):
            message = type("Message", (), {"content": "not-json"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(
        ai_engine,
        "AI",
        SimpleNamespace(api_key="test-key", timeout_seconds=1, validate=lambda: None),
    )
    monkeypatch.setattr(ai_engine, "AsyncOpenAI", lambda **_kwargs: FakeClient())

    proposal = await ai_engine.propose_trade("EURUSD", {"h1": {}}, [])

    assert proposal.action == ProposalAction.HOLD
    assert proposal.symbol == "EURUSD"
