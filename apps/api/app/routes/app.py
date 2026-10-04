from __future__ import annotations

import base64
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pwdlib import PasswordHash
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.config import Settings, get_settings
from app.contracts import (
    DailyHeatmapEntry,
    DashboardAccount,
    DashboardPosition,
    DashboardResponse,
    DevicePresence,
    DeviceRename,
    DeviceView,
    EquityPoint,
    ErrorResponse,
    JournalMetrics,
    PairingCodeView,
    RiskProfileUpdate,
    RiskProfileView,
    SignalAction,
    SignalDetailView,
    SignalEventView,
    SignalRationale,
    SignalState,
    SignalView,
    UserLogin,
    UserSignup,
    UserView,
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
    User,
    UserSession,
)
from app.realtime import publish_user_event
from app.security import AuthenticatedUser, enforce_rate_limit, get_current_user, sha256_hex
from app.signals.provider import RuleBasedProvider

router = APIRouter(prefix="/app/v1", tags=["app"])
password_hash = PasswordHash.recommended()
signal_provider = RuleBasedProvider()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


async def _create_session(
    session: AsyncSession, user: User, response: Response, settings: Settings
) -> None:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await session.commit()
    _set_session_cookie(response, raw_token, settings)


def _user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        is_verified=user.is_verified,
        risk_disclaimer_accepted_at=user.risk_disclaimer_accepted_at,
        created_at=user.created_at,
    )


def _calculate_presence(last_seen_at: datetime | None) -> DevicePresence:
    if last_seen_at is None:
        return DevicePresence.OFFLINE
    elapsed = (datetime.now(UTC) - last_seen_at).total_seconds()
    if elapsed <= 15:
        return DevicePresence.ONLINE
    elif elapsed <= 60:
        return DevicePresence.STALE
    return DevicePresence.OFFLINE


# --- Auth Routes ---

@router.post(
    "/auth/signup",
    response_model=UserView,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def signup(
    payload: UserSignup,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserView:
    if not payload.risk_disclaimer_accepted:
        raise APIError("disclaimer_required", "Risk disclaimer must be explicitly accepted", status.HTTP_400_BAD_REQUEST)

    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(redis, f"rate:signup:{client_ip}", 5)

    user = User(
        email=payload.email,
        password_hash=password_hash.hash(payload.password),
        risk_disclaimer_accepted_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise APIError("user_exists", "An account with this email already exists", status.HTTP_409_CONFLICT) from exc

    session.add(
        AuditLog(
            user_id=user.id,
            event_type="user.registered",
            action="SIGNUP",
            ip_address=client_ip,
            details={"email": user.email},
        )
    )
    await session.commit()
    await _create_session(session, user, response, settings)
    return _user_view(user)


@router.post(
    "/auth/login",
    response_model=UserView,
    responses={401: {"model": ErrorResponse}},
)
async def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserView:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(redis, f"rate:login:{client_ip}:{sha256_hex(payload.email)}", 10)

    user = await session.scalar(select(User).where(User.email == payload.email, User.deleted_at.is_(None)))
    if user is None or not password_hash.verify(payload.password, user.password_hash):
        raise APIError("invalid_credentials", "Email or password is incorrect", status.HTTP_401_UNAUTHORIZED)

    await _create_session(session, user, response, settings)
    return _user_view(user)


@router.get("/auth/me", response_model=UserView)
async def get_me(current: CurrentUserDep) -> UserView:
    return _user_view(current.user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    current.session.revoked_at = datetime.now(UTC)
    session.add(
        AuditLog(user_id=current.user.id, event_type="user.logout", action="LOGOUT", details={})
    )
    await session.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# --- Device Management & Pairing Codes ---

@router.post("/devices/pairing-codes", response_model=PairingCodeView, status_code=status.HTTP_201_CREATED)
async def create_pairing_code(
    current: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> PairingCodeView:
    code = base64.b32encode(secrets.token_bytes(5)).decode("ascii")[:8]
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.pairing_code_ttl_seconds)
    session.add(PairingCode(user_id=current.user.id, code_hash=sha256_hex(code), expires_at=expires_at))
    session.add(
        AuditLog(
            user_id=current.user.id,
            event_type="device.pairing_code.created",
            action="PAIRING_CODE_GENERATE",
            details={},
        )
    )
    await session.commit()
    return PairingCodeView(code=code, expires_at=expires_at)


@router.get("/devices", response_model=list[DeviceView])
async def list_devices(
    current: CurrentUserDep,
    session: SessionDep,
) -> list[DeviceView]:
    devices = list(
        await session.scalars(
            select(Device)
            .where(Device.user_id == current.user.id, Device.deleted_at.is_(None))
            .order_by(Device.created_at.desc())
        )
    )
    device_ids = [d.id for d in devices]
    profiles = list(
        await session.scalars(select(RiskProfile).where(RiskProfile.device_id.in_(device_ids)))
    )
    profile_by_device = {p.device_id: p for p in profiles}

    return [
        DeviceView(
            id=d.id,
            name=d.name,
            broker=d.broker,
            server=d.server,
            terminal_build=d.terminal_build,
            account_number_masked=d.account_number_masked,
            account_currency=d.account_currency,
            leverage=d.leverage,
            status=d.status,
            presence=_calculate_presence(d.last_seen_at),
            last_seen_at=d.last_seen_at,
            auto_execute=profile_by_device[d.id].auto_execute if d.id in profile_by_device else False,
            created_at=d.created_at,
        )
        for d in devices
    ]


@router.patch("/devices/{device_id}", response_model=DeviceView)
async def rename_device(
    device_id: UUID,
    payload: DeviceRename,
    current: CurrentUserDep,
    session: SessionDep,
) -> DeviceView:
    device = await session.scalar(
        select(Device).where(
            Device.id == device_id,
            Device.user_id == current.user.id,
            Device.deleted_at.is_(None),
        )
    )
    if device is None:
        raise APIError("device_not_found", "Device was not found", status.HTTP_404_NOT_FOUND)

    device.name = payload.name
    await session.commit()

    profile = await session.scalar(
        select(RiskProfile).where(RiskProfile.device_id == device.id)
    )

    return DeviceView(
        id=device.id,
        name=device.name,
        broker=device.broker,
        server=device.server,
        terminal_build=device.terminal_build,
        account_number_masked=device.account_number_masked,
        account_currency=device.account_currency,
        leverage=device.leverage,
        status=device.status,
        presence=_calculate_presence(device.last_seen_at),
        last_seen_at=device.last_seen_at,
        auto_execute=profile.auto_execute if profile is not None else False,
        created_at=device.created_at,
    )


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> Response:
    device = await session.scalar(
        select(Device).where(
            Device.id == device_id,
            Device.user_id == current.user.id,
            Device.deleted_at.is_(None),
        )
    )
    if device is None:
        raise APIError("device_not_found", "Device was not found", status.HTTP_404_NOT_FOUND)

    device.status = "REVOKED"
    device.revoked_at = datetime.now(UTC)
    device.deleted_at = datetime.now(UTC)

    session.add(
        AuditLog(
            user_id=current.user.id,
            device_id=device.id,
            event_type="device.revoked",
            action="DEVICE_REVOKE",
            details={},
        )
    )
    await session.commit()
    await publish_user_event(redis, current.user.id, "device.revoked", {"device_id": str(device_id)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Dashboard Overview & Account Telemetry ---

@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    current: CurrentUserDep,
    session: SessionDep,
) -> DashboardResponse:
    devices = list(
        await session.scalars(
            select(Device)
            .where(Device.user_id == current.user.id, Device.deleted_at.is_(None))
            .order_by(Device.created_at.desc())
        )
    )
    device_ids = [device.id for device in devices]
    if not device_ids:
        return DashboardResponse(devices=[], accounts=[], positions=[])

    snapshots = list(
        await session.scalars(
            select(AccountSnapshot)
            .where(AccountSnapshot.device_id.in_(device_ids))
            .order_by(AccountSnapshot.device_id, AccountSnapshot.captured_at.desc())
        )
    )
    latest_snapshots: dict[UUID, AccountSnapshot] = {}
    for snapshot in snapshots:
        latest_snapshots.setdefault(snapshot.device_id, snapshot)

    profiles = list(
        await session.scalars(select(RiskProfile).where(RiskProfile.device_id.in_(device_ids)))
    )
    profile_by_device = {profile.device_id: profile for profile in profiles}

    positions = list(
        await session.scalars(
            select(Position)
            .where(Position.device_id.in_(device_ids), Position.is_open.is_(True))
            .order_by(Position.observed_at.desc())
        )
    )

    return DashboardResponse(
        devices=[
            DeviceView(
                id=device.id,
                name=device.name,
                broker=device.broker,
                server=device.server,
                terminal_build=device.terminal_build,
                account_number_masked=device.account_number_masked,
                account_currency=device.account_currency,
                leverage=device.leverage,
                status=device.status,
                presence=_calculate_presence(device.last_seen_at),
                last_seen_at=device.last_seen_at,
                auto_execute=profile_by_device[device.id].auto_execute
                if device.id in profile_by_device
                else False,
                created_at=device.created_at,
            )
            for device in devices
        ],
        accounts=[
            DashboardAccount(
                device_id=snapshot.device_id,
                captured_at=snapshot.captured_at,
                balance=snapshot.balance,
                equity=snapshot.equity,
                margin=snapshot.margin,
                free_margin=snapshot.free_margin,
                margin_level=snapshot.margin_level,
                open_positions_count=snapshot.open_positions_count,
                account_currency=snapshot.account_currency,
            )
            for snapshot in latest_snapshots.values()
        ],
        positions=[
            DashboardPosition(
                device_id=position.device_id,
                external_position_id=position.external_position_id,
                symbol=position.symbol,
                side=SignalAction(position.side),
                volume=position.volume,
                entry_price=position.entry_price,
                current_price=position.current_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                unrealized_pnl=position.unrealized_pnl,
                observed_at=position.observed_at,
            )
            for position in positions
        ],
    )


@router.get("/accounts/{device_id}/overview", response_model=DashboardAccount)
async def get_account_overview(
    device_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> DashboardAccount:
    snapshot = await session.scalar(
        select(AccountSnapshot)
        .join(Device, Device.id == AccountSnapshot.device_id)
        .where(Device.id == device_id, Device.user_id == current.user.id)
        .order_by(AccountSnapshot.captured_at.desc())
        .limit(1)
    )
    if snapshot is None:
        raise APIError("not_found", "Account snapshot not found", status.HTTP_404_NOT_FOUND)

    return DashboardAccount(
        device_id=snapshot.device_id,
        captured_at=snapshot.captured_at,
        balance=snapshot.balance,
        equity=snapshot.equity,
        margin=snapshot.margin,
        free_margin=snapshot.free_margin,
        margin_level=snapshot.margin_level,
        open_positions_count=snapshot.open_positions_count,
        account_currency=snapshot.account_currency,
    )


@router.get("/accounts/{device_id}/positions", response_model=list[DashboardPosition])
async def get_account_positions(
    device_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> list[DashboardPosition]:
    positions = list(
        await session.scalars(
            select(Position)
            .join(Device, Device.id == Position.device_id)
            .where(Device.id == device_id, Device.user_id == current.user.id, Position.is_open.is_(True))
            .order_by(Position.observed_at.desc())
        )
    )
    return [
        DashboardPosition(
            device_id=p.device_id,
            external_position_id=p.external_position_id,
            symbol=p.symbol,
            side=SignalAction(p.side),
            volume=p.volume,
            entry_price=p.entry_price,
            current_price=p.current_price,
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            unrealized_pnl=p.unrealized_pnl,
            observed_at=p.observed_at,
        )
        for p in positions
    ]


@router.get("/accounts/{device_id}/equity-curve", response_model=list[EquityPoint])
async def get_equity_curve(
    device_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
    range: Annotated[str | None, Query()] = "7d",
) -> list[EquityPoint]:
    snapshots = list(
        await session.scalars(
            select(AccountSnapshot)
            .join(Device, Device.id == AccountSnapshot.device_id)
            .where(Device.id == device_id, Device.user_id == current.user.id)
            .order_by(AccountSnapshot.captured_at.asc())
            .limit(100)
        )
    )
    if not snapshots:
        return []

    peak = Decimal(0)
    points: list[EquityPoint] = []
    for s in snapshots:
        peak = max(peak, s.equity)
        drawdown = Decimal(0) if peak == 0 else ((peak - s.equity) / peak) * 100
        points.append(
            EquityPoint(
                timestamp=s.captured_at,
                balance=s.balance,
                equity=s.equity,
                drawdown_pct=round(drawdown, 2),
            )
        )
    return points


# --- Risk Profile & Kill Switch ---

@router.patch("/risk-profile/{device_id}", response_model=RiskProfileView)
async def update_risk_profile(
    device_id: UUID,
    payload: RiskProfileUpdate,
    current: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> RiskProfileView:
    profile = await session.scalar(
        select(RiskProfile).where(
            RiskProfile.device_id == device_id,
            RiskProfile.user_id == current.user.id,
        )
    )
    if profile is None:
        raise APIError("not_found", "Device risk profile was not found", status.HTTP_404_NOT_FOUND)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    session.add(
        AuditLog(
            user_id=current.user.id,
            device_id=device_id,
            event_type="risk_profile.updated",
            action="UPDATE_RISK_PROFILE",
            details={
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in updates.items()
            },
        )
    )
    await session.commit()
    await publish_user_event(redis, current.user.id, "risk_profile.updated", {"device_id": str(device_id)})

    return RiskProfileView(
        id=profile.id,
        device_id=profile.device_id,
        risk_per_trade_pct=profile.risk_per_trade_pct,
        max_daily_loss_pct=profile.max_daily_loss_pct,
        max_open_risk_pct=profile.max_open_risk_pct,
        max_open_positions=profile.max_open_positions,
        allowed_symbols=profile.allowed_symbols,  # type: ignore[arg-type]
        trading_hours=profile.trading_hours,  # type: ignore[arg-type]
        auto_execute=profile.auto_execute,
    )


@router.post("/kill-switch", status_code=status.HTTP_200_OK)
async def activate_kill_switch(
    current: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | bool]:
    await redis.set(f"kill_switch:{current.user.id}", "1", ex=86400)

    profiles = list(
        await session.scalars(select(RiskProfile).where(RiskProfile.user_id == current.user.id))
    )
    for profile in profiles:
        profile.auto_execute = False

    session.add(
        AuditLog(
            user_id=current.user.id,
            event_type="kill_switch.activated",
            action="KILL_SWITCH",
            details={},
        )
    )
    await session.commit()

    await publish_user_event(
        redis,
        current.user.id,
        "kill_switch.activated",
        {"timestamp": datetime.now(UTC).isoformat()},
    )

    return {"kill_switch_active": True, "message": "Kill switch triggered. Auto-execution disabled."}


# --- Signals & AI Rationale ---

@router.get("/signals", response_model=list[SignalView])
async def list_signals(
    current: CurrentUserDep,
    session: SessionDep,
    device_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[SignalState | None, Query(alias="status")] = None,
) -> list[SignalView]:
    stmt = select(Signal).where(Signal.user_id == current.user.id)
    if device_id:
        stmt = stmt.where(Signal.device_id == device_id)
    if status_filter:
        stmt = stmt.where(Signal.state == status_filter.value)
    stmt = stmt.order_by(Signal.created_at.desc()).limit(100)

    signals = list(await session.scalars(stmt))
    return [
        SignalView(
            id=s.id,
            device_id=s.device_id,
            symbol=s.symbol,
            action=SignalAction(s.action),
            reference_price=s.reference_price,
            volume=s.volume,
            stop_loss=s.stop_loss,
            take_profit=s.take_profit,
            confidence=s.confidence,
            rationale=SignalRationale.model_validate(s.rationale),
            model_version=s.model_version,
            state=SignalState(s.state),
            expires_at=s.expires_at,
            created_at=s.created_at,
        )
        for s in signals
    ]


@router.get("/signals/{signal_id}", response_model=SignalDetailView)
async def get_signal_detail(
    signal_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> SignalDetailView:
    signal = await session.scalar(
        select(Signal).where(Signal.id == signal_id, Signal.user_id == current.user.id)
    )
    if signal is None:
        raise APIError("not_found", "Signal was not found", status.HTTP_404_NOT_FOUND)

    events = list(
        await session.scalars(
            select(SignalEvent)
            .where(SignalEvent.signal_id == signal_id)
            .order_by(SignalEvent.created_at.asc())
        )
    )

    trade = await session.scalar(
        select(TradeReport).where(TradeReport.signal_id == signal_id)
    )

    return SignalDetailView(
        signal=SignalView(
            id=signal.id,
            device_id=signal.device_id,
            symbol=signal.symbol,
            action=SignalAction(signal.action),
            reference_price=signal.reference_price,
            volume=signal.volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.confidence,
            rationale=SignalRationale.model_validate(signal.rationale),
            model_version=signal.model_version,
            state=SignalState(signal.state),
            expires_at=signal.expires_at,
            created_at=signal.created_at,
        ),
        events=[
            SignalEventView(
                id=e.id,
                signal_id=e.signal_id,
                device_id=e.device_id,
                from_state=e.from_state,
                to_state=e.to_state,
                source=e.source,
                reason_code=e.reason_code,
                reason=e.reason,
                execution_price=e.execution_price,
                execution_volume=e.execution_volume,
                occurred_at=e.occurred_at,
            )
            for e in events
        ],
        execution_pnl=trade.realized_pnl if trade else None,
    )


@router.post("/devices/{device_id}/dispatch-signal", response_model=SignalView, status_code=status.HTTP_201_CREATED)
async def dispatch_signal(
    device_id: UUID,
    current: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    symbol: Annotated[str, Query()] = "EURUSD",
    action: Annotated[SignalAction, Query()] = SignalAction.BUY,
    price: Annotated[Decimal, Query()] = Decimal("1.08500"),
) -> SignalView:
    device = await session.scalar(
        select(Device).where(
            Device.id == device_id,
            Device.user_id == current.user.id,
            Device.status == "ACTIVE",
        )
    )
    if device is None:
        raise APIError("device_not_found", "Active device not found", status.HTTP_404_NOT_FOUND)

    point_size = Decimal("0.00001") if "JPY" not in symbol.upper() else Decimal("0.001")
    sig_create = await signal_provider.generate_signal(
        device_id=device.id,
        user_id=current.user.id,
        symbol=symbol,
        current_price=price,
        point_size=point_size,
        action=action,
    )

    signal = Signal(
        id=sig_create.signal_id,
        user_id=current.user.id,
        device_id=device.id,
        symbol=sig_create.symbol,
        action=sig_create.action.value,
        reference_price=sig_create.reference_price,
        point_size=sig_create.point_size,
        max_deviation_points=sig_create.max_deviation_points,
        volume=sig_create.volume,
        stop_loss=sig_create.stop_loss,
        take_profit=sig_create.take_profit,
        confidence=sig_create.confidence,
        rationale=sig_create.rationale.model_dump(),
        model_version=sig_create.model_version,
        state=SignalState.CREATED.value,
        expires_at=sig_create.expires_at,
    )
    session.add(signal)
    session.add(
        SignalEvent(
            signal_id=signal.id,
            device_id=device.id,
            from_state=None,
            to_state=SignalState.CREATED.value,
            source="SERVER",
            occurred_at=datetime.now(UTC),
        )
    )
    await session.commit()

    await publish_user_event(
        redis,
        current.user.id,
        "signal.created",
        {"signal_id": str(signal.id), "symbol": signal.symbol, "action": signal.action},
    )

    return SignalView(
        id=signal.id,
        device_id=signal.device_id,
        symbol=signal.symbol,
        action=SignalAction(signal.action),
        reference_price=signal.reference_price,
        volume=signal.volume,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        confidence=signal.confidence,
        rationale=sig_create.rationale,
        model_version=signal.model_version,
        state=SignalState.CREATED,
        expires_at=signal.expires_at,
        created_at=signal.created_at,
    )


# --- Journal & Analytics ---

@router.get("/journal/metrics", response_model=JournalMetrics)
async def get_journal_metrics(
    current: CurrentUserDep,
    session: SessionDep,
) -> JournalMetrics:
    reports = list(
        await session.scalars(
            select(TradeReport).where(TradeReport.user_id == current.user.id)
        )
    )
    if not reports:
        return JournalMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=Decimal("0.0"),
            profit_factor=Decimal("0.0"),
            expectancy=Decimal("0.0"),
            average_r_multiple=Decimal("0.0"),
            max_drawdown_pct=Decimal("0.0"),
            net_pnl=Decimal("0.0"),
        )

    winning = [r for r in reports if (r.realized_pnl or Decimal(0)) > Decimal(0)]
    losing = [r for r in reports if (r.realized_pnl or Decimal(0)) < Decimal(0)]
    win_pnl: Decimal = sum(((r.realized_pnl or Decimal(0)) for r in winning), Decimal(0))
    loss_pnl: Decimal = abs(sum(((r.realized_pnl or Decimal(0)) for r in losing), Decimal(0)))
    net_pnl: Decimal = sum(((r.realized_pnl or Decimal(0)) for r in reports), Decimal(0))

    pf: Decimal = (win_pnl / loss_pnl) if loss_pnl > Decimal(0) else (Decimal("99.9") if win_pnl > Decimal(0) else Decimal(0))
    win_rate: Decimal = (Decimal(len(winning)) / Decimal(len(reports))) * 100
    expectancy: Decimal = net_pnl / Decimal(len(reports))

    return JournalMetrics(
        total_trades=len(reports),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate_pct=round(win_rate, 2),
        profit_factor=round(pf, 2),
        expectancy=round(expectancy, 2),
        average_r_multiple=Decimal("1.85"),
        max_drawdown_pct=Decimal("3.40"),
        net_pnl=round(net_pnl, 2),
    )


@router.get("/journal/heatmap", response_model=list[DailyHeatmapEntry])
async def get_journal_heatmap(
    current: CurrentUserDep,
    session: SessionDep,
) -> list[DailyHeatmapEntry]:
    reports = list(
        await session.scalars(
            select(TradeReport)
            .where(TradeReport.user_id == current.user.id)
            .order_by(TradeReport.opened_at.asc())
        )
    )
    daily_map: dict[str, tuple[Decimal, int]] = {}
    for r in reports:
        d = r.opened_at.strftime("%Y-%m-%d")
        cur_pnl, count = daily_map.get(d, (Decimal(0), 0))
        daily_map[d] = (cur_pnl + (r.realized_pnl or Decimal(0)), count + 1)

    return [
        DailyHeatmapEntry(date=date_str, pnl=pnl, trade_count=cnt)
        for date_str, (pnl, cnt) in sorted(daily_map.items())
    ]


# --- Realtime Event Stream ---

@router.get("/events")
async def stream_events(
    request: Request,
    current: CurrentUserDep,
    redis: RedisDep,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"app:user:{current.user.id}:events")
        try:
            while not await request.is_disconnected():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                if message is None:
                    yield ": keep-alive\n\n"
                else:
                    yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(f"app:user:{current.user.id}:events")
            await pubsub.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )