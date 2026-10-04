import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.contracts import SignalAction, SignalEventType, SignalState
from app.main import app
from app.models import Base, Device, PairingCode, Position, RiskProfile, Signal, User, UserSession
from app.security import sha256_hex, sign_ea_request


@pytest.fixture
async def test_app():
    # Set up in-memory sqlite engine for integration tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis

    try:
        yield app
    finally:
        try:
            await redis.flushdb()
            await redis.aclose()
        except Exception:
            pass
        await engine.dispose()


@pytest.mark.asyncio
async def test_complete_ea_lifecycle(test_app):
    session_factory = test_app.state.session_factory
    redis = test_app.state.redis

    # 1. Create a user and pairing code
    user_id = uuid4()
    code = "AQ-TEST88"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="trader@test.com",
            password_hash="argon2_placeholder",
            risk_disclaimer_accepted_at=datetime.now(UTC),
        )
        pairing_code = PairingCode(
            user_id=user_id,
            code_hash=sha256_hex(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        session.add(user)
        session.add(pairing_code)
        await session.commit()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. EA Pairing
        pair_res = await client.post(
            "/ea/v1/pair",
            json={
                "code": code,
                "terminal_build": "4150",
                "broker": "MetaQuotes-Demo",
                "server": "Demo-Server",
                "account_number_masked": "5091****12",
                "account_currency": "USD",
                "leverage": 100,
            },
        )
        assert pair_res.status_code == 200
        pair_data = pair_res.json()
        device_id = pair_data["device_id"]
        device_token = pair_data["device_token"]
        assert device_token is not None

        # 3. EA Heartbeat (Signed)
        ts = str(int(time.time()))
        nonce = "nonce_heartbeat_1"
        body = {
            "snapshot": {
                "balance": "10000.00",
                "equity": "10050.25",
                "margin": "200.00",
                "free_margin": "9850.25",
                "margin_level": "5025.12",
                "open_positions_count": 1,
                "account_currency": "USD",
                "leverage": 100,
                "captured_at": datetime.now(UTC).isoformat(),
            },
            "positions": [
                {
                    "external_position_id": "TICKET_101",
                    "symbol": "EURUSD",
                    "side": "BUY",
                    "volume": "0.10",
                    "entry_price": "1.08500",
                    "current_price": "1.08550",
                    "stop_loss": "1.08200",
                    "take_profit": "1.09100",
                    "unrealized_pnl": "50.00",
                    "swap": "0.25",
                    "observed_at": datetime.now(UTC).isoformat(),
                }
            ],
        }
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=body).content
        sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", ts, nonce, raw_body)

        hb_res = await client.post(
            "/ea/v1/heartbeat",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert hb_res.status_code == 200
        hb_data = hb_res.json()
        assert hb_data["accepted"] is True

        # 4. Replay Attack Prevention (Same Nonce)
        replay_res = await client.post(
            "/ea/v1/heartbeat",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert replay_res.status_code == 401

        # 5. Timestamp Drift Rejection (> 30s)
        stale_ts = str(int(time.time()) - 45)
        stale_nonce = "nonce_stale_ts_99"
        stale_sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", stale_ts, stale_nonce, raw_body)
        stale_res = await client.post(
            "/ea/v1/heartbeat",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": stale_ts,
                "X-EA-Nonce": stale_nonce,
                "X-EA-Signature": stale_sig,
            },
        )
        assert stale_res.status_code == 401
