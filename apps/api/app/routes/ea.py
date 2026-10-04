from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.config import Settings, get_settings
from app.contracts import (
    EAPairRequest,
    EAPairResponse,
    ErrorResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    SignalAckRequest,
    SignalAckResponse,
    SignalDelivery,
    SignalRationale,
    SignalState,
    TradeReportInput,
)
from app.database import get_redis, get_session
from app.errors import APIError
from app.models import (
    AccountSnapshot,
    AuditLog,
    Device,
    PairingCode,
    Position,
    RiskProfile,
    Signal,
    SignalEvent,
    TradeReport,
)
from app.realtime import publish_user_event
from app.security import (
    AuthenticatedDevice,
    enforce_rate_limit,
    get_current_device,
    sha256_hex,
)

router = APIRouter(prefix="/ea/v1", tags=["ea"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentDeviceDep = Annotated[AuthenticatedDevice, Depends(get_current_device)]


@router.post(
    "/pair",
    response_model=EAPairResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def pair_device(
    payload: EAPairRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> EAPairResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(redis, f"rate:ea:pair:{client_ip}", 10)

    code_hash = sha256_hex(payload.code)
    pairing_code = await session.scalar(
        select(PairingCode).where(
            PairingCode.code_hash == code_hash,
            PairingCode.consumed_at.is_(None),
            PairingCode.expires_at > datetime.now(UTC),
        )
    )
    if pairing_code is None:
        raise APIError("invalid_pairing_code", "Pairing code is invalid or expired", status.HTTP_401_UNAUTHORIZED)

    pairing_code.consumed_at = datetime.now(UTC)

    raw_device_token = secrets.token_hex(32)  # 256-bit entropy
    token_hash = sha256_hex(raw_device_token)

    device = Device(
        user_id=pairing_code.user_id,
        token_hash=token_hash,
        terminal_build=payload.terminal_build,
        broker=payload.broker,
        server=payload.server,
        account_number_masked=payload.account_number_masked,
        account_currency=payload.account_currency.upper(),
        leverage=payload.leverage,
        status="ACTIVE",
        last_seen_at=datetime.now(UTC),
    )
    session.add(device)
    await session.flush()

    risk_profile = RiskProfile(
        user_id=pairing_code.user_id,
        device_id=device.id,
        risk_per_trade_pct=Decimal("0.5000"),
        max_daily_loss_pct=Decimal("2.0000"),
        max_open_risk_pct=Decimal("3.0000"),
        max_open_positions=5,
        auto_execute=False,
    )
    session.add(risk_profile)

    session.add(
        AuditLog(
            user_id=pairing_code.user_id,
            device_id=device.id,
            event_type="device.paired",
            action="PAIR",
            ip_address=client_ip,
            details={
                "broker": payload.broker,
                "server": payload.server,
                "account_number_masked": payload.account_number_masked,
            },
        )
    )
    await session.commit()

    await publish_user_event(
        redis,
        pairing_code.user_id,
        "device.paired",
        {
            "device_id": str(device.id),
            "broker": device.broker,
            "server": device.server,
            "account_number_masked": device.account_number_masked,
        },
    )

    return EAPairResponse(
        device_id=device.id,
        device_token=raw_device_token,
        token_type="AegisQuant-HMAC-SHA256",
        token_shown_once=True,
    )


@router.post(
    "/heartbeat",
    response_model=HeartbeatResponse,
    responses={401: {"model": ErrorResponse}},
)
async def heartbeat(
    payload: HeartbeatRequest,
    current_device: CurrentDeviceDep,
    session: SessionDep,
    redis: RedisDep,
) -> HeartbeatResponse:
    device = current_device.device
    now = datetime.now(UTC)
    device.last_seen_at = now

    snapshot = AccountSnapshot(
        device_id=device.id,
        balance=payload.snapshot.balance,
        equity=payload.snapshot.equity,
        margin=payload.snapshot.margin,
        free_margin=payload.snapshot.free_margin,
        margin_level=payload.snapshot.margin_level,
        open_positions_count=len(payload.positions),
        account_currency=payload.snapshot.account_currency,
        leverage=payload.snapshot.leverage,
        captured_at=payload.snapshot.captured_at,
    )
    session.add(snapshot)

    # Update open positions
    existing_positions = list(
        await session.scalars(
            select(Position).where(Position.device_id == device.id, Position.is_open.is_(True))
        )
    )
    existing_map = {pos.external_position_id: pos for pos in existing_positions}
    incoming_ids = set()

    for pos_in in payload.positions:
        incoming_ids.add(pos_in.external_position_id)
        if pos_in.external_position_id in existing_map:
            pos = existing_map[pos_in.external_position_id]
            pos.current_price = pos_in.current_price
            pos.stop_loss = pos_in.stop_loss
            pos.take_profit = pos_in.take_profit
            pos.unrealized_pnl = pos_in.unrealized_pnl
            pos.swap = pos_in.swap
            pos.observed_at = pos_in.observed_at
        else:
            session.add(
                Position(
                    device_id=device.id,
                    external_position_id=pos_in.external_position_id,
                    symbol=pos_in.symbol,
                    side=pos_in.side.value,
                    volume=pos_in.volume,
                    entry_price=pos_in.entry_price,
                    current_price=pos_in.current_price,
                    stop_loss=pos_in.stop_loss,
                    take_profit=pos_in.take_profit,
                    unrealized_pnl=pos_in.unrealized_pnl,
                    swap=pos_in.swap,
                    magic_number=pos_in.magic_number,
                    comment=pos_in.comment,
                    observed_at=pos_in.observed_at,
                    is_open=True,
                )
            )

    # Mark closed positions
    for ext_id, pos in existing_map.items():
        if ext_id not in incoming_ids:
            pos.is_open = False
            pos.observed_at = now

    risk_profile = await session.scalar(
        select(RiskProfile).where(RiskProfile.device_id == device.id)
    )
    auto_execute = risk_profile.auto_execute if risk_profile else False

    # Check kill-switch flag in Redis
    kill_switch_active = bool(await redis.get(f"kill_switch:{device.user_id}"))

    await session.commit()

    await publish_user_event(
        redis,
        device.user_id,
        "account.telemetry",
        {
            "device_id": str(device.id),
            "balance": str(payload.snapshot.balance),
            "equity": str(payload.snapshot.equity),
            "free_margin": str(payload.snapshot.free_margin),
            "open_positions": len(payload.positions),
            "timestamp": now.isoformat(),
        },
    )

    return HeartbeatResponse(
        accepted=True,
        server_time=now,
        auto_execute=auto_execute,
        kill_switch=kill_switch_active,
    )


@router.get(
    "/signals",
    response_model=list[SignalDelivery],
    responses={401: {"model": ErrorResponse}},
)
async def poll_signals(
    current_device: CurrentDeviceDep,
    session: SessionDep,
    since: Annotated[str | None, Query()] = None,
) -> list[SignalDelivery]:
    device = current_device.device
    now = datetime.now(UTC)

    signals = list(
        await session.scalars(
            select(Signal)
            .where(
                Signal.device_id == device.id,
                Signal.state.in_([SignalState.CREATED.value, SignalState.DELIVERED.value]),
                Signal.expires_at > now,
            )
            .order_by(Signal.created_at.asc())
        )
    )

    deliveries: list[SignalDelivery] = []
    risk_profile = await session.scalar(
        select(RiskProfile).where(RiskProfile.device_id == device.id)
    )
    auto_execute = risk_profile.auto_execute if risk_profile else False

    for sig in signals:
        if sig.state == SignalState.CREATED.value:
            sig.state = SignalState.DELIVERED.value
            session.add(
                SignalEvent(
                    signal_id=sig.id,
                    device_id=device.id,
                    from_state=SignalState.CREATED.value,
                    to_state=SignalState.DELIVERED.value,
                    source="SERVER",
                    occurred_at=now,
                )
            )

        deliveries.append(
            SignalDelivery(
                signal_id=sig.id,
                symbol=sig.symbol,
                action=sig.action,  # type: ignore[arg-type]
                reference_price=sig.reference_price,
                point_size=sig.point_size,
                max_deviation_points=sig.max_deviation_points,
                volume=sig.volume,
                stop_loss=sig.stop_loss,
                take_profit=sig.take_profit,
                confidence=sig.confidence,
                rationale=SignalRationale.model_validate(sig.rationale),
                model_version=sig.model_version,
                expires_at=sig.expires_at,
                auto_execute=auto_execute,
            )
        )

    await session.commit()
    return deliveries


@router.post(
    "/signals/{signal_id}/ack",
    response_model=SignalAckResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def ack_signal(
    signal_id: UUID,
    payload: SignalAckRequest,
    current_device: CurrentDeviceDep,
    session: SessionDep,
    redis: RedisDep,
) -> SignalAckResponse:
    device = current_device.device
    signal = await session.scalar(
        select(Signal).where(Signal.id == signal_id, Signal.device_id == device.id)
    )
    if signal is None:
        raise APIError("signal_not_found", "Signal not found for this device", status.HTTP_404_NOT_FOUND)

    prev_state = signal.state
    new_state = payload.event.value

    signal.state = new_state
    session.add(
        SignalEvent(
            signal_id=signal.id,
            device_id=device.id,
            from_state=prev_state,
            to_state=new_state,
            source="EA",
            reason_code=payload.reason_code,
            reason=payload.reason,
            execution_price=payload.execution_price,
            execution_volume=payload.execution_volume,
            occurred_at=payload.occurred_at,
        )
    )
    await session.commit()

    await publish_user_event(
        redis,
        device.user_id,
        "signal.state_changed",
        {
            "signal_id": str(signal.id),
            "device_id": str(device.id),
            "state": new_state,
            "reason_code": payload.reason_code,
        },
    )

    return SignalAckResponse(signal_id=signal.id, state=SignalState(new_state), accepted=True)


@router.post(
    "/trade-reports",
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}},
)
async def create_trade_report(
    payload: TradeReportInput,
    current_device: CurrentDeviceDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | bool]:
    device = current_device.device

    report = TradeReport(
        user_id=device.user_id,
        device_id=device.id,
        signal_id=payload.signal_id,
        external_order_id=payload.ticket,
        symbol=payload.symbol,
        side=payload.side.value,
        volume=payload.volume,
        entry_price=payload.execution_price,
        exit_price=payload.exit_price,
        slippage_points=payload.slippage_points,
        commission=payload.commission,
        swap=payload.swap,
        realized_pnl=payload.profit,
        opened_at=payload.opened_at,
        closed_at=payload.closed_at,
    )
    session.add(report)
    await session.commit()

    await publish_user_event(
        redis,
        device.user_id,
        "trade.reported",
        {
            "device_id": str(device.id),
            "ticket": payload.ticket,
            "symbol": payload.symbol,
            "profit": str(payload.profit) if payload.profit is not None else None,
        },
    )

    return {"accepted": True}
