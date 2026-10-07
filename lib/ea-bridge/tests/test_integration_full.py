import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.contracts import (
    SignalAction,
    SignalEventType,
    SignalState,
)
from app.main import app
from app.models import (
    AccountSnapshot,
    AuditLog,
    Base,
    Device,
    PairingCode,
    Position,
    RiskProfile,
    Signal,
    SignalEvent,
    TradeReport,
    User,
    UserSession,
)
from app.security import sha256_hex, sign_ea_request
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


@pytest.fixture
async def test_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis
    get_settings().session_cookie_secure = False

    try:
        yield app
    finally:
        try:
            await redis.flushdb()
            await redis.aclose()
        except Exception:
            pass
        await engine.dispose()


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def session_factory(test_app):
    return test_app.state.session_factory


@pytest.fixture
async def redis_client(test_app):
    return test_app.state.redis


async def _create_user(session_factory, email="trader@test.com", password="SecurePass123!"):
    user_id = uuid4()
    async with session_factory() as session:
        user = User(
            id=user_id,
            email=email,
            password_hash=password_hash.hash(password),
            risk_disclaimer_accepted_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
    return user_id, password


async def _login(client, email, password):
    resp = await client.post("/app/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp


async def _create_device(session_factory, user_id):
    device_id = uuid4()
    async with session_factory() as session:
        device = Device(
            id=device_id,
            user_id=user_id,
            token_hash=sha256_hex("device-token-" + str(device_id)),
            broker="TestBroker",
            server="TestServer",
            account_number_masked="1234****56",
            account_currency="USD",
            leverage=100,
            status="ACTIVE",
            last_seen_at=datetime.now(UTC),
        )
        profile = RiskProfile(
            user_id=user_id,
            device_id=device_id,
            risk_per_trade_pct=Decimal("0.5"),
            max_daily_loss_pct=Decimal("2.0"),
            max_open_risk_pct=Decimal("3.0"),
            max_open_positions=5,
            auto_execute=False,
        )
        session.add(device)
        session.add(profile)
        await session.commit()
    return device_id


async def _auth_client(client, session_factory, user_id):
    raw_token = "test-token-" + str(uuid4())
    async with session_factory() as session:
        session.add(UserSession(
            user_id=user_id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        ))
        await session.commit()
    client.cookies.set("aegis_session", raw_token)
    return client


# --- INT-01..INT-14 style app-route coverage ---

@pytest.mark.asyncio
async def test_signup_returns_201_and_session_cookie(client):
    resp = await client.post(
        "/app/v1/auth/signup",
        json={"email": "new@test.com", "password": "SecurePass123!", "risk_disclaimer_accepted": True},
    )
    assert resp.status_code == 201
    assert resp.cookies.get("aegis_session") is not None


@pytest.mark.asyncio
async def test_login_returns_401_bad_credentials(client):
    resp = await client.post("/app/v1/auth/login", json={"email": "nobody@test.com", "password": "bad"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_requires_cookie(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get("/app/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "trader@test.com"


@pytest.mark.asyncio
async def test_logout_revokes_session(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.post("/app/v1/auth/logout")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_pairing_code_201(client, session_factory):
    await _create_user(session_factory)
    await _login(client, "trader@test.com", "SecurePass123!")
    resp = await client.post("/app/v1/devices/pairing-codes")
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["code"]) == 8


@pytest.mark.asyncio
async def test_list_devices_empty_200(client, session_factory):
    await _create_user(session_factory)
    await _login(client, "trader@test.com", "SecurePass123!")
    resp = await client.get("/app/v1/devices")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_rename_device_200(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.patch(f"/app/v1/devices/{device_id}", json={"name": "My MT5"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "My MT5"


@pytest.mark.asyncio
async def test_revoke_device_204(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.delete(f"/app/v1/devices/{device_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_dashboard_200(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get("/app/v1/dashboard")
    assert resp.status_code == 200
    assert resp.json()["devices"] == []


@pytest.mark.asyncio
async def test_account_overview_404_when_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get(f"/app/v1/accounts/{device_id}/overview")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_account_positions_200_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get(f"/app/v1/accounts/{device_id}/positions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_equity_curve_200_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get(f"/app/v1/accounts/{device_id}/equity-curve")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_update_risk_profile_200(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.patch(
        f"/app/v1/risk-profile/{device_id}",
        json={"risk_per_trade_pct": "1.0000", "auto_execute": True},
    )
    assert resp.status_code == 200
    assert resp.json()["auto_execute"] is True


@pytest.mark.asyncio
async def test_kill_switch_200(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.post("/app/v1/kill-switch")
    assert resp.status_code == 200
    assert resp.json()["kill_switch_active"] is True


@pytest.mark.asyncio
async def test_list_signals_200_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get("/app/v1/signals")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_signal_detail_404(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get(f"/app/v1/signals/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dispatch_signal_201(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    device_id = await _create_device(session_factory, user_id)
    await _auth_client(client, session_factory, user_id)
    resp = await client.post(f"/app/v1/devices/{device_id}/dispatch-signal?symbol=EURUSD&action=BUY")
    assert resp.status_code == 201
    assert resp.json()["symbol"] == "EURUSD"


@pytest.mark.asyncio
async def test_journal_metrics_200_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get("/app/v1/journal/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_trades"] == 0


@pytest.mark.asyncio
async def test_journal_heatmap_200_empty(client, session_factory):
    user_id, _ = await _create_user(session_factory)
    await _auth_client(client, session_factory, user_id)
    resp = await client.get("/app/v1/journal/heatmap")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_events_stream_401_without_auth(client):
    resp = await client.get("/app/v1/events")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_healthz_200(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readyz_200_requires_redis(client, session_factory, redis_client):
    await redis_client.ping()
    resp = await client.get("/readyz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthorized_error_code_is_raised(client):
    resp = await client.get("/app/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_ea_pair_endpoint_returns_token_once(test_app):
    session_factory = test_app.state.session_factory
    redis = test_app.state.redis
    user_id = uuid4()
    code = "AQ-COVER99"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="ea@test.com",
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
        first = await client.post(
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
        assert first.status_code == 200
        first_token = first.json()["device_token"]

        second = await client.post(
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
        assert second.status_code == 401
        assert second.json()["code"] == "invalid_pairing_code"


@pytest.mark.asyncio
async def test_ea_heartbeat_rejected_when_device_revoked(test_app):
    session_factory = test_app.state.session_factory
    redis = test_app.state.redis
    user_id = uuid4()
    code = "AQ-REVOKE1"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="revoke@test.com",
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
        pair = await client.post(
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
        assert pair.status_code == 200
        device_id = pair.json()["device_token"]

        async with session_factory() as session:
            actual_device = await session.scalar(select(Device).where(Device.id == UUID(pair.json()["device_id"])))
            actual_device.status = "REVOKED"
            await session.commit()

        ts = str(int(time.time()))
        nonce = "nonce_revoke_1"
        body = b'{"snapshot":{"balance":"10000.00","equity":"10050.25","margin":"200.00","free_margin":"9850.25","margin_level":null,"open_positions_count":0,"account_currency":"USD","leverage":100,"captured_at":"2026-01-01T00:00:00+00:00"},"positions":[]}'
        sig = sign_ea_request(device_id, "POST", "/ea/v1/heartbeat", ts, nonce, body)

        hb = await client.post(
            "/ea/v1/heartbeat",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_id,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert hb.status_code == 401
        assert hb.json()["code"] == "invalid_device_auth"


@pytest.mark.asyncio
async def test_ea_poll_signals_200_empty(test_app):
    session_factory = test_app.state.session_factory
    user_id = uuid4()
    code = "AQ-SIGNAL1"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="signal@test.com",
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
        pair = await client.post(
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
        assert pair.status_code == 200
        token = pair.json()["device_token"]

        ts = str(int(time.time()))
        nonce = "nonce_signals_01"
        body = b""
        sig = sign_ea_request(token, "GET", "/ea/v1/signals", ts, nonce, body)

        resp = await client.get(
            "/ea/v1/signals",
            headers={
                "X-EA-Device-Token": token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_ea_ack_signal_404(test_app):
    session_factory = test_app.state.session_factory
    user_id = uuid4()
    code = "AQ-ACK01"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="ack@test.com",
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
        pair = await client.post(
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
        assert pair.status_code == 200
        token = pair.json()["device_token"]

        signal_id = uuid4()
        ts = str(int(time.time()))
        nonce = "nonce_ack_000001"
        body = b'{"event":"ACKED","occurred_at":"2026-01-01T00:00:00+00:00"}'
        sig = sign_ea_request(token, "POST", f"/ea/v1/signals/{signal_id}/ack", ts, nonce, body)

        resp = await client.post(
            f"/ea/v1/signals/{signal_id}/ack",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "signal_not_found"


@pytest.mark.asyncio
async def test_ea_trade_report_201(test_app):
    session_factory = test_app.state.session_factory
    user_id = uuid4()
    code = "AQ-TRADE1"
    async with session_factory() as session:
        user = User(
            id=user_id,
            email="trade@test.com",
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
        pair = await client.post(
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
        assert pair.status_code == 200
        token = pair.json()["device_token"]

        ts = str(int(time.time()))
        nonce = "nonce_trade_000001"
        body = (
            b'{"signal_id":"' + str(uuid4()).encode() + b'","ticket":"TICKET_1","symbol":"EURUSD","side":"BUY","volume":"0.10","execution_price":"1.08500","opened_at":"2026-01-01T00:00:00+00:00"}'
        )
        sig = sign_ea_request(token, "POST", "/ea/v1/trade-reports", ts, nonce, body)

        resp = await client.post(
            "/ea/v1/trade-reports",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["accepted"] is True
