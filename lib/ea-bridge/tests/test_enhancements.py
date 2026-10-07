"""
Verification Suite for High-Impact Enhancements:
1. Macroeconomic News Calendar & Blackout Filter
2. Telegram/Discord Notification Dispatcher
3. Prop-Firm Compliance Monitoring & Drawdown Tracker
4. News API Endpoints & Route Integrity
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models import (
    AccountSnapshot,
    Base,
    Device,
    PairingCode,
    RiskProfile,
    User,
    UserSession,
)
from app.news import MacroNewsService, NewsEvent, macro_news_service
from app.notifications import NotificationService, notification_service
from app.security import sha256_hex


# ---------------------------------------------------------------------------
# Unit Tests for MacroNewsService
# ---------------------------------------------------------------------------

def test_news_blackout_detection():
    service = MacroNewsService()
    now = datetime.now(UTC)

    # Add a high-impact USD event 15 minutes in the future
    event = NewsEvent(
        id="test-nfp-1",
        title="US Non-Farm Payrolls",
        currency="USD",
        impact="HIGH",
        scheduled_at=now + timedelta(minutes=15),
    )
    service.add_event(event)

    # Check EURUSD (has USD) -> Blackout should be TRUE
    status_eurusd = service.check_blackout("EURUSD", target_time=now)
    assert status_eurusd.is_blackout is True
    assert status_eurusd.affected_currency == "USD"
    assert "US Non-Farm Payrolls" in status_eurusd.event_title

    # Check EURGBP (neither is USD) -> Blackout should be FALSE
    status_eurgbp = service.check_blackout("EURGBP", target_time=now)
    assert status_eurgbp.is_blackout is False


def test_news_blackout_post_event_window():
    service = MacroNewsService()
    now = datetime.now(UTC)

    # Event happened 5 minutes ago (within 15 min post-event window)
    event = NewsEvent(
        id="test-cpi-1",
        title="US CPI YoY",
        currency="USD",
        impact="HIGH",
        scheduled_at=now - timedelta(minutes=5),
    )
    service.add_event(event)

    status = service.check_blackout("USDJPY", target_time=now)
    assert status.is_blackout is True

    # Event happened 45 minutes ago (outside post-event window)
    status_past = service.check_blackout("USDJPY", target_time=now + timedelta(minutes=45))
    assert status_past.is_blackout is False


# ---------------------------------------------------------------------------
# Unit Tests for NotificationService
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_formatting_without_webhook():
    service = NotificationService()
    # When webhook_url is None, gracefully returns False without error
    res_open = await service.notify_trade_opened(
        None,
        ticket="12345",
        symbol="EURUSD",
        side="BUY",
        volume=Decimal("0.50"),
        price=Decimal("1.08500"),
        sl=Decimal("1.08200"),
        tp=Decimal("1.09100"),
    )
    assert res_open is False

    res_close = await service.notify_trade_closed(
        None,
        ticket="12345",
        symbol="EURUSD",
        realized_pnl=Decimal("250.00"),
    )
    assert res_close is False

    res_ks = await service.notify_kill_switch(
        None,
        user_id=uuid4(),
    )
    assert res_ks is False


# ---------------------------------------------------------------------------
# Integration Tests for New Endpoints (News & Prop-Firm Compliance)
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool | None = None, **kwargs) -> bool:
        if nx and key in self._data:
            return False
        self._data[key] = value
        return True

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def publish(self, channel: str, message: str) -> int:
        return 0

    async def aclose(self) -> None:
        pass


@pytest.fixture
async def app_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    fake_redis = FakeRedis()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = fake_redis

    yield app, session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_news_endpoints(app_env):
    test_app, sf = app_env

    # Create user
    user_id = uuid4()
    raw_token = "sess-news-" + str(uuid4())
    async with sf() as session:
        user = User(
            id=user_id,
            email="news@example.com",
            password_hash="argon2_hash",
            risk_disclaimer_accepted_at=datetime.now(UTC),
        )
        sess = UserSession(
            user_id=user_id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        session.add(user)
        session.add(sess)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.cookies.set("aegis_session", raw_token)

        # 1. GET /app/v1/news/calendar
        cal_resp = await client.get("/app/v1/news/calendar")
        assert cal_resp.status_code == 200, cal_resp.text
        data = cal_resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)
        assert len(data["events"]) > 0

        # 2. GET /app/v1/news/blackout-check
        check_resp = await client.get("/app/v1/news/blackout-check", params={"symbol": "EURUSD"})
        assert check_resp.status_code == 200, check_resp.text
        check_data = check_resp.json()
        assert "is_blackout" in check_data
        assert check_data["symbol"] == "EURUSD"


@pytest.mark.asyncio
async def test_prop_firm_compliance_status(app_env):
    test_app, sf = app_env

    user_id = uuid4()
    device_id = uuid4()
    raw_token = "sess-prop-" + str(uuid4())

    async with sf() as session:
        user = User(
            id=user_id,
            email="propfirm@example.com",
            password_hash="argon2_hash",
            risk_disclaimer_accepted_at=datetime.now(UTC),
        )
        sess = UserSession(
            user_id=user_id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        device = Device(
            id=device_id,
            user_id=user_id,
            token_hash="fake_hash",
            broker="MetaQuotes-Demo",
            server="Demo-Server",
            account_number_masked="1234****56",
            account_currency="USD",
            leverage=100,
            status="ACTIVE",
        )
        risk = RiskProfile(
            device_id=device_id,
            user_id=user_id,
            risk_per_trade_pct=Decimal("1.0"),
            max_daily_loss_pct=Decimal("4.5"),  # 4.5% FTMO limit
            max_open_risk_pct=Decimal("5.0"),
            max_open_positions=5,
            auto_execute=True,
        )
        # Snapshot with $10,000 balance and $9,700 equity (3% drawdown)
        snapshot = AccountSnapshot(
            device_id=device_id,
            balance=Decimal("10000.00"),
            equity=Decimal("9700.00"),
            margin=Decimal("200.00"),
            free_margin=Decimal("9500.00"),
            margin_level=Decimal("4850.00"),
            open_positions_count=1,
            account_currency="USD",
            leverage=100,
            captured_at=datetime.now(UTC),
        )
        session.add(user)
        session.add(sess)
        session.add(device)
        session.add(risk)
        session.add(snapshot)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.cookies.set("aegis_session", raw_token)

        resp = await client.get(f"/app/v1/accounts/{device_id}/prop-firm-status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["device_id"] == str(device_id)
        assert data["prop_firm_mode_enabled"] is True
        assert Decimal(data["starting_daily_balance"]) == Decimal("10000.00")
        assert Decimal(data["current_equity"]) == Decimal("9700.00")
        assert Decimal(data["daily_drawdown_pct"]) == Decimal("3.0000")
        assert data["drawdown_breached"] is False
        assert Decimal(data["remaining_drawdown_budget"]) == Decimal("150.00")
