"""
Verification Layer 2 — Integration Tests INT-01 … INT-14

Each test maps 1-to-1 to the INT-xx IDs in the verification plan.
Run with:
    cd lib/ea-bridge
    PYTHONPATH=. pytest tests/test_verification_int.py -v
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.contracts import SignalAction, SignalEventType, SignalState
from app.main import app
from app.models import (
    Base,
    Device,
    PairingCode,
    Signal,
    SignalEvent,
    User,
    UserSession,
)
from app.security import sha256_hex, sign_ea_request

# ---------------------------------------------------------------------------
# Fake Redis — supports incr/expire/get/set/delete/publish/setnx
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal async-compatible Redis fake for test isolation."""

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

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool | None = None,
        **kwargs,
    ) -> bool:
        if nx:
            if key in self._data:
                return False
            self._data[key] = value
            return True
        self._data[key] = value
        return True

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._counters.pop(key, None)

    async def publish(self, channel: str, message: str) -> int:
        return 0

    async def flushdb(self) -> None:
        self._data.clear()
        self._counters.clear()

    async def aclose(self) -> None:
        pass

    def pipeline(self):
        return self

    async def execute(self):
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Shared fixtures & helpers
# ---------------------------------------------------------------------------

_PAIR_PAYLOAD = {
    "terminal_build": "4150",
    "broker": "MetaQuotes-Demo",
    "server": "Demo-Server",
    "account_number_masked": "5091****99",
    "account_currency": "USD",
    "leverage": 100,
}


def _hb_body(dt: datetime | None = None) -> dict:
    ts = (dt or datetime.now(UTC)).isoformat()
    return {
        "snapshot": {
            "balance": "10000.00",
            "equity": "10000.00",
            "margin": "0.00",
            "free_margin": "10000.00",
            "margin_level": "0.00",
            "open_positions_count": 0,
            "account_currency": "USD",
            "leverage": 100,
            "captured_at": ts,
        },
        "positions": [],
    }


@pytest.fixture
async def env():
    """
    Yield (app, session_factory, fake_redis).
    Uses an in-memory SQLite DB and FakeRedis for pure unit/integration isolation.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    fake_redis = FakeRedis()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = fake_redis

    try:
        yield app, session_factory, fake_redis
    finally:
        await fake_redis.flushdb()
        await engine.dispose()


async def _create_user(
    session_factory, *, email: str = "trader@example.com"
) -> tuple[User, str]:
    """Create a user and a session; return (user, raw_session_token)."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email=email,
            password_hash="argon2_placeholder",
            risk_disclaimer_accepted_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()

        raw_token = "raw-session-" + str(uuid4())
        sess = UserSession(
            user_id=user.id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        session.add(sess)
        await session.commit()
        return user, raw_token


async def _create_pairing_code(
    session_factory, user_id, *, code: str = "AQ-INT0001"
) -> str:
    async with session_factory() as session:
        pc = PairingCode(
            user_id=user_id,
            code_hash=sha256_hex(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        session.add(pc)
        await session.commit()
    return code


async def _pair_device(client: AsyncClient, code: str) -> tuple[str, str]:
    """Pair a device; return (device_id, device_token)."""
    resp = await client.post("/ea/v1/pair", json={"code": code, **_PAIR_PAYLOAD})
    assert resp.status_code == 200, f"Pair failed: {resp.text}"
    data = resp.json()
    return data["device_id"], data["device_token"]


# ---------------------------------------------------------------------------
# INT-01 – Pair with a valid code → 200; token returned once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_01_pair_valid_code(env):
    """INT-01: Pair with a valid code → 200; token + device_id returned."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int01@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0101")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/ea/v1/pair", json={"code": code, **_PAIR_PAYLOAD})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "device_token" in data
    assert "device_id" in data
    assert len(data["device_token"]) == 64  # 256-bit hex token


# ---------------------------------------------------------------------------
# INT-02 – Reuse the same pairing code → rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_02_pairing_code_single_use(env):
    """INT-02: Reusing a consumed pairing code is rejected."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int02@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0201")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        first = await client.post("/ea/v1/pair", json={"code": code, **_PAIR_PAYLOAD})
        assert first.status_code == 200, first.text

        second = await client.post("/ea/v1/pair", json={"code": code, **_PAIR_PAYLOAD})

    assert second.status_code in (401, 409), second.text
    assert second.json()["code"] in ("invalid_pairing_code", "pairing_code_used"), second.json()


# ---------------------------------------------------------------------------
# INT-03 – Pair with an expired code → rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_03_pairing_code_expired(env):
    """INT-03: An expired pairing code is rejected."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int03@example.com")

    async with sf() as session:
        pc = PairingCode(
            user_id=user.id,
            code_hash=sha256_hex("AQ-INT0301"),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),  # already expired
        )
        session.add(pc)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/ea/v1/pair", json={"code": "AQ-INT0301", **_PAIR_PAYLOAD})

    assert resp.status_code in (401, 410), resp.text
    assert resp.json()["code"] in (
        "invalid_pairing_code",
        "pairing_code_expired",
    ), resp.json()


# ---------------------------------------------------------------------------
# INT-04 – Heartbeat with a bad signature → 401 invalid_signature
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_04_heartbeat_bad_signature(env):
    """INT-04: A tampered/wrong HMAC signature is rejected."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int04@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0401")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        _, device_token = await _pair_device(client, code)

        hb = _hb_body()
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=hb).content
        ts = str(int(time.time()))
        nonce = "nonce-int04-" + str(uuid4())

        resp = await client.post(
            "/ea/v1/heartbeat",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": "deadbeef" * 8,  # intentionally wrong
            },
        )

    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] in ("invalid_signature", "invalid_device_auth"), resp.json()


# ---------------------------------------------------------------------------
# INT-05 – Replay an identical signed request → 401 replayed_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_05_nonce_replay(env):
    """INT-05: Replaying the same nonce is rejected."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int05@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0501")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        _, device_token = await _pair_device(client, code)

        hb = _hb_body()
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=hb).content
        ts = str(int(time.time()))
        nonce = "fixed-replay-nonce-" + str(uuid4())
        sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", ts, nonce, raw_body)
        headers = {
            "Content-Type": "application/json",
            "X-EA-Device-Token": device_token,
            "X-EA-Timestamp": ts,
            "X-EA-Nonce": nonce,
            "X-EA-Signature": sig,
        }

        first = await client.post("/ea/v1/heartbeat", content=raw_body, headers=headers)
        assert first.status_code == 200, first.text

        second = await client.post("/ea/v1/heartbeat", content=raw_body, headers=headers)

    assert second.status_code == 401, second.text
    assert second.json()["code"] in ("replayed_request", "nonce_replay"), second.json()


# ---------------------------------------------------------------------------
# INT-06 – Timestamp 31 s old → 401 stale_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_06_clock_skew(env):
    """INT-06: A timestamp older than 30 s is rejected."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int06@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0601")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        _, device_token = await _pair_device(client, code)

        hb = _hb_body()
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=hb).content
        stale_ts = str(int(time.time()) - 31)
        nonce = "nonce-skew-" + str(uuid4())
        sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", stale_ts, nonce, raw_body)

        resp = await client.post(
            "/ea/v1/heartbeat",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": stale_ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            },
        )

    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] in ("stale_request", "clock_skew"), resp.json()


# ---------------------------------------------------------------------------
# INT-07 – Heartbeat from a revoked device → 401/403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_07_revoked_device_heartbeat(env):
    """INT-07: A revoked device is rejected at the next heartbeat."""
    test_app, sf, _ = env
    user, session_token = await _create_user(sf, email="int07@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0701")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        # Revoke via app API
        client.cookies.set("aegis_session", session_token)
        revoke_resp = await client.delete(f"/app/v1/devices/{device_id}")
        assert revoke_resp.status_code == 204, revoke_resp.text

        # Heartbeat should now fail
        hb = _hb_body()
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=hb).content
        ts = str(int(time.time()))
        nonce = "nonce-revoke-" + str(uuid4())
        sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", ts, nonce, raw_body)

        resp = await client.post(
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

    assert resp.status_code in (401, 403), resp.text
    assert resp.json()["code"] in (
        "invalid_device_auth",
        "device_revoked",
    ), resp.json()


# ---------------------------------------------------------------------------
# INT-08 – Illegal transition EXECUTED → DELIVERED refused (DB guard)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_08_illegal_state_transition(env):
    """INT-08: Signal state must not regress from EXECUTED to DELIVERED."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int08@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0801")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        signal_id = uuid4()
        async with sf() as session:
            sig = Signal(
                id=signal_id,
                user_id=user.id,
                device_id=UUID(device_id),
                symbol="EURUSD",
                action="BUY",
                reference_price=Decimal("1.08500"),
                point_size=Decimal("0.00001"),
                max_deviation_points=20,
                volume=Decimal("0.01"),
                stop_loss=Decimal("1.08200"),
                take_profit=Decimal("1.09000"),
                confidence=0.75,
                rationale={
                    "summary": "test",
                    "factors": [],
                    "model_version": "test-v1",
                },
                model_version="test-v1",
                state=SignalState.EXECUTED.value,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            session.add(sig)
            session.add(
                SignalEvent(
                    signal_id=signal_id,
                    device_id=UUID(device_id),
                    from_state=SignalState.DELIVERED.value,
                    to_state=SignalState.EXECUTED.value,
                    source="EA",
                    occurred_at=datetime.now(UTC),
                )
            )
            await session.commit()

        # Attempt backward ACK
        ack_payload = {
            "event": "DELIVERED",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        raw_ack = client.build_request(
            "POST", f"/ea/v1/signals/{signal_id}/ack", json=ack_payload
        ).content
        ts = str(int(time.time()))
        nonce = "nonce-int08-ack-" + str(uuid4())
        ack_sig = sign_ea_request(
            device_token, "POST", f"/ea/v1/signals/{signal_id}/ack", ts, nonce, raw_ack
        )
        await client.post(
            f"/ea/v1/signals/{signal_id}/ack",
            content=raw_ack,
            headers={
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": ack_sig,
            },
        )

    # The critical assertion: DB state must NOT have regressed to DELIVERED
    from sqlalchemy import select as sa_select

    async with sf() as session:
        refreshed = (await session.scalars(sa_select(Signal).where(Signal.id == signal_id))).first()
    assert refreshed is not None
    assert refreshed.state != SignalState.DELIVERED.value, (
        "Signal state regressed from EXECUTED to DELIVERED — state machine guard is missing"
    )


# ---------------------------------------------------------------------------
# INT-09 – Signal past its expiry is not returned by /ea/v1/signals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_09_expired_signal_not_returned(env):
    """INT-09: An expired signal must not appear in the EA poll response."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int09@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT0901")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        signal_id = uuid4()
        async with sf() as session:
            session.add(
                Signal(
                    id=signal_id,
                    user_id=user.id,
                    device_id=UUID(device_id),
                    symbol="EURUSD",
                    action="BUY",
                    reference_price=Decimal("1.08500"),
                    point_size=Decimal("0.00001"),
                    max_deviation_points=20,
                    volume=Decimal("0.01"),
                    stop_loss=Decimal("1.08200"),
                    take_profit=Decimal("1.09000"),
                    confidence=0.75,
                    rationale={
                        "summary": "test",
                        "factors": [],
                        "model_version": "test-v1",
                    },
                    model_version="test-v1",
                    state=SignalState.CREATED.value,
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),  # expired
                )
            )
            await session.commit()

        raw_body = b""
        ts = str(int(time.time()))
        nonce = "nonce-int09-poll-" + str(uuid4())
        sig_hdr = sign_ea_request(device_token, "GET", "/ea/v1/signals", ts, nonce, raw_body)
        poll_resp = await client.get(
            "/ea/v1/signals",
            headers={
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig_hdr,
            },
        )

    assert poll_resp.status_code == 200, poll_resp.text
    returned_ids = [s["signal_id"] for s in poll_resp.json()]
    assert str(signal_id) not in returned_ids, "Expired signal must not appear in poll response"


# ---------------------------------------------------------------------------
# INT-10 – Duplicate trade report → at most one DB row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_10_duplicate_trade_report(env):
    """INT-10: Submitting the same trade report twice leaves at most one DB row."""
    test_app, sf, _ = env
    user, _ = await _create_user(sf, email="int10@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT1001")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        report = {
            "ticket": "TICKET-INT10",
            "symbol": "EURUSD",
            "side": "BUY",
            "volume": "0.01",
            "execution_price": "1.08510",
            "opened_at": datetime.now(UTC).isoformat(),
        }
        raw_body = client.build_request("POST", "/ea/v1/trade-reports", json=report).content

        def _headers(nonce: str) -> dict:
            ts = str(int(time.time()))
            sig = sign_ea_request(device_token, "POST", "/ea/v1/trade-reports", ts, nonce, raw_body)
            return {
                "Content-Type": "application/json",
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig,
            }

        first = await client.post(
            "/ea/v1/trade-reports",
            content=raw_body,
            headers=_headers("nonce-tr-1-" + str(uuid4())),
        )
        assert first.status_code in (200, 201), first.text

        second = await client.post(
            "/ea/v1/trade-reports",
            content=raw_body,
            headers=_headers("nonce-tr-2-" + str(uuid4())),
        )
        assert second.status_code in (200, 201, 204, 409), second.text

    from app.models import TradeReport
    from sqlalchemy import select as sa_select

    async with sf() as session:
        rows = list(
            await session.scalars(
                sa_select(TradeReport).where(TradeReport.external_order_id == "TICKET-INT10")
            )
        )
    assert len(rows) <= 1, f"Expected ≤1 trade report row, got {len(rows)}"


# ---------------------------------------------------------------------------
# INT-11 – Kill switch on → next heartbeat carries kill_switch: true
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_11_kill_switch_reflected_in_heartbeat(env):
    """INT-11: Activating the kill switch is reflected in the EA heartbeat response."""
    test_app, sf, _ = env
    user, session_token = await _create_user(sf, email="int11@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT1101")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        # Activate kill switch via app API
        client.cookies.set("aegis_session", session_token)
        ks_resp = await client.post("/app/v1/kill-switch", json={"active": True})
        assert ks_resp.status_code == 200, ks_resp.text

        # Send heartbeat
        hb = _hb_body()
        raw_body = client.build_request("POST", "/ea/v1/heartbeat", json=hb).content
        ts = str(int(time.time()))
        nonce = "nonce-ks-hb-" + str(uuid4())
        sig = sign_ea_request(device_token, "POST", "/ea/v1/heartbeat", ts, nonce, raw_body)

        hb_resp = await client.post(
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

    assert hb_resp.status_code == 200, hb_resp.text
    assert hb_resp.json().get("kill_switch") is True, (
        f"Expected kill_switch=true in heartbeat response, got: {hb_resp.json()}"
    )


# ---------------------------------------------------------------------------
# INT-12 – Risk check: symbol not allowed → signal not delivered to EA
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_12_risk_check_symbol_not_allowed(env):
    """INT-12: A signal for a symbol outside allowed_symbols must not be delivered."""
    test_app, sf, _ = env
    user, session_token = await _create_user(sf, email="int12@example.com")
    code = await _create_pairing_code(sf, user.id, code="AQ-INT1201")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        device_id, device_token = await _pair_device(client, code)

        # Set risk profile to only allow EURUSD
        client.cookies.set("aegis_session", session_token)
        await client.patch(
            f"/app/v1/risk-profile/{device_id}",
            json={
                "allowed_symbols": ["EURUSD"],
                "risk_per_trade_pct": "1.0",
                "max_open_risk_pct": "5.0",
                "auto_execute": True,
            },
        )

        # Directly insert a GBPUSD signal into the DB (bypassing the server)
        signal_id = uuid4()
        async with sf() as session:
            session.add(
                Signal(
                    id=signal_id,
                    user_id=user.id,
                    device_id=UUID(device_id),
                    symbol="GBPUSD",
                    action="BUY",
                    reference_price=Decimal("1.27000"),
                    point_size=Decimal("0.00001"),
                    max_deviation_points=20,
                    volume=Decimal("0.01"),
                    stop_loss=Decimal("1.26700"),
                    take_profit=Decimal("1.28000"),
                    confidence=0.70,
                    rationale={
                        "summary": "test",
                        "factors": [],
                    },
                    model_version="test-v1",
                    state=SignalState.CREATED.value,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            )
            await session.commit()

        # Poll as the EA
        raw_body = b""
        ts = str(int(time.time()))
        nonce = "nonce-int12-poll-" + str(uuid4())
        sig_hdr = sign_ea_request(device_token, "GET", "/ea/v1/signals", ts, nonce, raw_body)
        poll_resp = await client.get(
            "/ea/v1/signals",
            headers={
                "X-EA-Device-Token": device_token,
                "X-EA-Timestamp": ts,
                "X-EA-Nonce": nonce,
                "X-EA-Signature": sig_hdr,
            },
        )

    assert poll_resp.status_code == 200, poll_resp.text
    gbpusd_signals = [s for s in poll_resp.json() if s.get("symbol") == "GBPUSD"]
    assert len(gbpusd_signals) == 0, (
        "GBPUSD signal was delivered even though allowed_symbols=[EURUSD]."
    )


# ---------------------------------------------------------------------------
# INT-13 – Rate limit exceeded → 429 rate_limited
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_13_rate_limit(env):
    """INT-13: Exceed the pairing rate limit (10 req/min) → 429."""
    test_app, sf, fake_redis = env
    user, _ = await _create_user(sf, email="int13@example.com")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        last_resp = None
        for i in range(12):
            resp = await client.post("/ea/v1/pair", json={"code": f"AQ-INT13{i:02d}", **_PAIR_PAYLOAD})
            last_resp = resp
            if resp.status_code == 429:
                break

    assert last_resp is not None
    assert last_resp.status_code == 429, (
        f"Expected 429 after 11 requests, got {last_resp.status_code}: {last_resp.text}"
    )
    assert last_resp.json()["code"] in ("rate_limited", "too_many_requests"), last_resp.json()


# ---------------------------------------------------------------------------
# INT-14 – Two users — strict resource isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_INT_14_user_isolation(env):
    """INT-14: User A must not be able to read or modify user B's resources."""
    test_app, sf, _ = env

    user_a, token_a = await _create_user(sf, email="int14a@example.com")
    user_b, token_b = await _create_user(sf, email="int14b@example.com")
    code_b = await _create_pairing_code(sf, user_b.id, code="AQ-INT1401")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # Pair a device for user B
        device_id_b, _ = await _pair_device(client, code_b)

        # Now act as user A
        client.cookies.set("aegis_session", token_a)

        # 1. Devices list — must NOT include B's device
        devices_resp = await client.get("/app/v1/devices")
        assert devices_resp.status_code == 200, devices_resp.text
        device_ids = [d["id"] for d in devices_resp.json()]
        assert device_id_b not in device_ids, "User A must not see user B's devices"

        # 2. Revoke B's device — must be 403 or 404
        revoke_resp = await client.delete(f"/app/v1/devices/{device_id_b}")
        assert revoke_resp.status_code in (403, 404), (
            f"User A revoked user B's device — got {revoke_resp.status_code}"
        )

        # 3. Account overview — must be 403 or 404
        overview_resp = await client.get(f"/app/v1/accounts/{device_id_b}/overview")
        assert overview_resp.status_code in (403, 404), (
            f"User A read user B's account overview — got {overview_resp.status_code}"
        )

        # 4. Risk profile update — must be 403 or 404
        risk_resp = await client.patch(
            f"/app/v1/risk-profile/{device_id_b}",
            json={
                "risk_per_trade_pct": "2.0",
                "max_open_risk_pct": "5.0",
                "auto_execute": False,
            },
        )
        assert risk_resp.status_code in (403, 404), (
            f"User A updated user B's risk profile — got {risk_resp.status_code}"
        )

        # 5. Signals list — only A's signals (none) must appear
        signals_resp = await client.get("/app/v1/signals")
        assert signals_resp.status_code == 200, signals_resp.text
        from app.models import Signal as SignalModel
        from sqlalchemy import select as sa_select

        async with sf() as session:
            b_signal_ids = [
                str(s.id)
                for s in await session.scalars(
                    sa_select(SignalModel).where(SignalModel.user_id == user_b.id)
                )
            ]
        returned_ids = [s["id"] for s in signals_resp.json()]
        cross_signals = [sid for sid in returned_ids if sid in b_signal_ids]
        assert len(cross_signals) == 0, f"User A received user B's signals: {cross_signals}"
