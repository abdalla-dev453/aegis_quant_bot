from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveMoney = Annotated[Decimal, Field(ge=Decimal(0), max_digits=24, decimal_places=8)]
SignedMoney = Annotated[Decimal, Field(max_digits=24, decimal_places=8)]
Price = Annotated[Decimal, Field(gt=Decimal(0), max_digits=28, decimal_places=12)]
Volume = Annotated[Decimal, Field(gt=Decimal(0), max_digits=20, decimal_places=8)]
ConfidenceScore = Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1), max_digits=5, decimal_places=4)]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorResponse(APIModel):
    code: str
    message: str
    details: dict[str, str | int | float | bool | None] | None = None


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalState(StrEnum):
    CREATED = "CREATED"
    DELIVERED = "DELIVERED"
    ACKED = "ACKED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DeviceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class DevicePresence(StrEnum):
    ONLINE = "ONLINE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"


# --- User & Auth Contracts ---

class UserSignup(APIModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    risk_disclaimer_accepted: bool

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.lower()
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[1]:
            raise ValueError("A valid email address is required")
        return normalized


class UserLogin(APIModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserView(APIModel):
    id: UUID
    email: str
    is_verified: bool
    risk_disclaimer_accepted_at: datetime
    created_at: datetime


class PairingCodeView(APIModel):
    code: str
    expires_at: datetime


# --- EA Bridge Contracts (/ea/v1/*) ---

class EAPairRequest(APIModel):
    code: str = Field(min_length=8, max_length=16, pattern=r"^[A-Z0-9_-]{8,16}$")
    terminal_build: str = Field(min_length=1, max_length=32)
    broker: str = Field(min_length=1, max_length=120)
    server: str = Field(min_length=1, max_length=120)
    account_number_masked: str = Field(min_length=1, max_length=64)
    account_currency: str = Field(min_length=3, max_length=8)
    leverage: int = Field(ge=1, le=100_000)


class EAPairResponse(APIModel):
    device_id: UUID
    device_token: str
    token_type: str = "AegisQuant-HMAC-SHA256"
    token_shown_once: bool = True


class AccountSnapshotInput(APIModel):
    balance: PositiveMoney
    equity: PositiveMoney
    margin: PositiveMoney = Decimal(0)
    free_margin: PositiveMoney
    margin_level: Decimal | None = None
    open_positions_count: int = Field(ge=0, default=0)
    account_currency: str = Field(min_length=3, max_length=8)
    leverage: int = Field(ge=1, le=100_000)
    captured_at: datetime


class PositionInput(APIModel):
    external_position_id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=3, max_length=32)
    side: SignalAction
    volume: Volume
    entry_price: Price
    current_price: Price
    stop_loss: Price | None = None
    take_profit: Price | None = None
    unrealized_pnl: SignedMoney
    swap: SignedMoney = Decimal(0)
    magic_number: int | None = None
    comment: str | None = Field(default=None, max_length=120)
    observed_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class HeartbeatRequest(APIModel):
    snapshot: AccountSnapshotInput
    positions: list[PositionInput] = Field(max_length=500)


class HeartbeatResponse(APIModel):
    accepted: bool
    server_time: datetime
    auto_execute: bool
    kill_switch: bool = False


# --- Signal Engine Contracts ---

class SignalRationaleFactor(APIModel):
    name: str
    weight: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    description: str


class SignalRationale(APIModel):
    summary: str
    factors: list[SignalRationaleFactor] = Field(default_factory=list)


class SignalCreate(APIModel):
    device_id: UUID
    signal_id: UUID
    symbol: str = Field(min_length=3, max_length=32)
    action: SignalAction
    reference_price: Price
    point_size: Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=12)]
    max_deviation_points: int = Field(ge=0, le=100_000)
    volume: Volume
    stop_loss: Price
    take_profit: Price
    confidence: ConfidenceScore = Decimal("0.8500")
    rationale: SignalRationale
    model_version: str = Field(default="v1.0-rule-based", max_length=64)
    expires_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class SignalDelivery(APIModel):
    signal_id: UUID
    symbol: str
    action: SignalAction
    reference_price: Price
    point_size: Decimal
    max_deviation_points: int
    volume: Volume
    stop_loss: Price
    take_profit: Price
    confidence: ConfidenceScore
    rationale: SignalRationale
    model_version: str
    expires_at: datetime
    auto_execute: bool


class SignalEventType(StrEnum):
    ACKED = "ACKED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class SignalAckRequest(APIModel):
    event: SignalEventType
    occurred_at: datetime
    execution_price: Price | None = None
    execution_volume: Volume | None = None
    reason_code: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class SignalAckResponse(APIModel):
    signal_id: UUID
    state: SignalState
    accepted: bool


class SignalView(APIModel):
    id: UUID
    device_id: UUID
    symbol: str
    action: SignalAction
    reference_price: Price
    volume: Volume
    stop_loss: Price
    take_profit: Price
    confidence: ConfidenceScore
    rationale: SignalRationale
    model_version: str
    state: SignalState
    expires_at: datetime
    created_at: datetime


class SignalEventView(APIModel):
    id: UUID
    signal_id: UUID
    device_id: UUID
    from_state: str | None
    to_state: str
    source: str
    reason_code: str | None
    reason: str | None
    execution_price: Price | None
    execution_volume: Volume | None
    occurred_at: datetime


# --- Risk Profile Contracts ---

class RiskProfileView(APIModel):
    id: UUID
    device_id: UUID
    risk_per_trade_pct: Decimal
    max_daily_loss_pct: Decimal
    max_open_risk_pct: Decimal
    max_open_positions: int
    allowed_symbols: list[str] | None = None
    trading_hours: dict[str, str | int | float | bool | None] | None = None
    auto_execute: bool


class RiskProfileUpdate(APIModel):
    risk_per_trade_pct: Annotated[Decimal, Field(gt=0, le=5, max_digits=8, decimal_places=4)] | None = None
    max_daily_loss_pct: Annotated[Decimal, Field(gt=0, le=100, max_digits=8, decimal_places=4)] | None = None
    max_open_risk_pct: Annotated[Decimal, Field(gt=0, le=100, max_digits=8, decimal_places=4)] | None = None
    max_open_positions: Annotated[int, Field(ge=1, le=50)] | None = None
    allowed_symbols: list[str] | None = None
    trading_hours: dict[str, str | int | float | bool | None] | None = None
    auto_execute: bool | None = None


# --- Device Management Contracts ---

class DeviceView(APIModel):
    id: UUID
    name: str
    broker: str
    server: str
    terminal_build: str | None
    account_number_masked: str
    account_currency: str
    leverage: int
    status: str
    presence: DevicePresence
    last_seen_at: datetime | None
    auto_execute: bool
    created_at: datetime


class DeviceRename(APIModel):
    name: str = Field(min_length=1, max_length=100)


# --- Trade Reports & Analytics Contracts ---

class TradeReportInput(APIModel):
    signal_id: UUID | None = None
    ticket: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=3, max_length=32)
    side: SignalAction
    volume: Volume
    execution_price: Price
    exit_price: Price | None = None
    slippage_points: Decimal | None = None
    commission: SignedMoney = Decimal(0)
    swap: SignedMoney = Decimal(0)
    profit: SignedMoney | None = None
    opened_at: datetime
    closed_at: datetime | None = None


class TradeReportView(APIModel):
    id: UUID
    signal_id: UUID | None
    device_id: UUID
    ticket: str
    symbol: str
    side: SignalAction
    volume: Volume
    execution_price: Price
    exit_price: Price | None
    slippage_points: Decimal | None
    commission: SignedMoney
    swap: SignedMoney
    realized_pnl: SignedMoney | None
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime


# --- Audit Log Contracts ---

class AuditLogView(APIModel):
    id: UUID
    user_id: UUID | None
    device_id: UUID | None
    event_type: str
    action: str | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    details: dict[str, str | int | float | bool | None]
    created_at: datetime


# --- Dashboard Overview Contracts ---

class DashboardAccount(APIModel):
    device_id: UUID
    captured_at: datetime
    balance: PositiveMoney
    equity: PositiveMoney
    margin: PositiveMoney
    free_margin: PositiveMoney
    margin_level: Decimal | None
    open_positions_count: int
    account_currency: str


class DashboardPosition(APIModel):
    device_id: UUID
    external_position_id: str
    symbol: str
    side: SignalAction
    volume: Volume
    entry_price: Price
    current_price: Price
    stop_loss: Price | None
    take_profit: Price | None
    unrealized_pnl: SignedMoney
    observed_at: datetime


class DashboardResponse(APIModel):
    devices: list[DeviceView]
    accounts: list[DashboardAccount]
    positions: list[DashboardPosition]