from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts import (
    EAPairRequest,
    ErrorResponse,
    HeartbeatRequest,
    PositionInput,
    RiskProfileUpdate,
    SignalAckRequest,
    SignalAction,
    SignalCreate,
    SignalRationale,
    SignalRationaleFactor,
    SignalState,
    UserSignup,
)


def test_error_response_contract() -> None:
    err = ErrorResponse(code="rate_limited", message="Too many requests", details={"limit": 100})
    assert err.code == "rate_limited"
    assert err.message == "Too many requests"
    assert err.details == {"limit": 100}

    dumped = err.model_dump(exclude_none=True)
    assert dumped == {
        "code": "rate_limited",
        "message": "Too many requests",
        "details": {"limit": 100},
    }


def test_user_signup_validation() -> None:
    valid = UserSignup(
        email="Trader@AegisQuant.com",
        password="SecurePassword123!",
        risk_disclaimer_accepted=True,
    )
    assert valid.email == "trader@aegisquant.com"

    with pytest.raises(ValidationError):
        UserSignup(
            email="invalid-email",
            password="SecurePassword123!",
            risk_disclaimer_accepted=True,
        )

    with pytest.raises(ValidationError):
        UserSignup(
            email="user@test.com",
            password="short",
            risk_disclaimer_accepted=True,
        )


def test_signal_creation_and_rationale() -> None:
    now = datetime.now(UTC)
    signal = SignalCreate(
        device_id=uuid4(),
        signal_id=uuid4(),
        symbol="eurusd",
        action=SignalAction.BUY,
        reference_price=Decimal("1.08500"),
        point_size=Decimal("0.00001"),
        max_deviation_points=20,
        volume=Decimal("0.10"),
        stop_loss=Decimal("1.08200"),
        take_profit=Decimal("1.09100"),
        confidence=Decimal("0.9200"),
        rationale=SignalRationale(
            summary="Strong bullish engulfing candle on H1 with positive momentum confluence.",
            factors=[
                SignalRationaleFactor(name="RSI Oversold", weight=Decimal("0.40"), description="RSI(14) < 30 on M15"),
                SignalRationaleFactor(name="EMA Trend", weight=Decimal("0.60"), description="Price above 200 EMA on H1"),
            ],
        ),
        expires_at=now + timedelta(seconds=30),
    )
    assert signal.symbol == "EURUSD"
    assert signal.action == SignalAction.BUY
    assert signal.confidence == Decimal("0.9200")
    assert len(signal.rationale.factors) == 2


def test_position_and_money_precision() -> None:
    pos = PositionInput(
        external_position_id="MT5_100293",
        symbol="gbpusd",
        side=SignalAction.SELL,
        volume=Decimal("0.50"),
        entry_price=Decimal("1.27500"),
        current_price=Decimal("1.27420"),
        unrealized_pnl=Decimal("40.00"),
        observed_at=datetime.now(UTC),
    )
    assert pos.symbol == "GBPUSD"
    assert pos.volume == Decimal("0.50")
    assert pos.unrealized_pnl == Decimal("40.00")


def test_ea_pairing_request_validation() -> None:
    req = EAPairRequest(
        code="AQ-982736",
        terminal_build="4150",
        broker="MetaQuotes-Demo",
        server="MetaQuotes-Server",
        account_number_masked="1092****83",
        account_currency="USD",
        leverage=100,
    )
    assert req.leverage == 100
    assert req.broker == "MetaQuotes-Demo"

    with pytest.raises(ValidationError):
        EAPairRequest(
            code="123",  # Too short
            terminal_build="4150",
            broker="Broker",
            server="Server",
            account_number_masked="1092",
            account_currency="USD",
            leverage=0,  # Invalid leverage
        )
