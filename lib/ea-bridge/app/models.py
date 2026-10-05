from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class User(Timestamped, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    risk_disclaimer_accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    two_factor_secret: Mapped[str | None] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Timestamped, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_expires", "user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PairingCode(Timestamped, Base):
    __tablename__ = "pairing_codes"
    __table_args__ = (
        Index("ix_pairing_codes_user_expires", "user_id", "expires_at"),
        Index("ix_pairing_codes_expires", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Timestamped, Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_user_status_last_seen", "user_id", "status", "last_seen_at"),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_devices_status"),
        CheckConstraint("leverage >= 1", name="ck_devices_leverage_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="MT5 Terminal")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_build: Mapped[str | None] = mapped_column(String(32))
    broker: Mapped[str] = mapped_column(String(120), nullable=False)
    server: Mapped[str] = mapped_column(String(120), nullable=False)
    account_number_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    account_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountSnapshot(Timestamped, Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (
        Index("ix_account_snapshots_device_captured", "device_id", "captured_at"),
        CheckConstraint("balance >= 0", name="ck_account_snapshots_balance_nonnegative"),
        CheckConstraint("equity >= 0", name="ck_account_snapshots_equity_nonnegative"),
        CheckConstraint("free_margin >= 0", name="ck_account_snapshots_margin_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    margin: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    free_margin: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    margin_level: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    open_positions_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    account_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Position(Timestamped, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("device_id", "external_position_id", name="uq_positions_device_external"),
        Index("ix_positions_device_open_observed", "device_id", "is_open", "observed_at"),
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_positions_side"),
        CheckConstraint("volume > 0", name="ck_positions_volume_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    external_position_id: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    swap: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    magic_number: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class RiskProfile(Timestamped, Base):
    __tablename__ = "risk_profiles"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_risk_profiles_device"),
        CheckConstraint("risk_per_trade_pct > 0 AND risk_per_trade_pct <= 5", name="ck_risk_profiles_trade_risk"),
        CheckConstraint("max_daily_loss_pct > 0 AND max_daily_loss_pct <= 100", name="ck_risk_profiles_daily_loss"),
        CheckConstraint("max_open_risk_pct > 0 AND max_open_risk_pct <= 100", name="ck_risk_profiles_open_risk"),
        CheckConstraint("max_open_positions >= 1 AND max_open_positions <= 50", name="ck_risk_profiles_max_positions"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    risk_per_trade_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, server_default="0.5000"
    )
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, server_default="2.0000"
    )
    max_open_risk_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, server_default="3.0000"
    )
    max_open_positions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    allowed_symbols: Mapped[list[JSONValue] | None] = mapped_column(JSON)
    trading_hours: Mapped[dict[str, JSONValue] | None] = mapped_column(JSON)
    auto_execute: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Signal(Timestamped, Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_device_state_expires", "device_id", "state", "expires_at"),
        CheckConstraint("action IN ('BUY', 'SELL')", name="ck_signals_action"),
        CheckConstraint(
            "state IN ('CREATED', 'DELIVERED', 'ACKED', 'EXECUTED', 'REJECTED', 'EXPIRED')",
            name="ck_signals_state",
        ),
        CheckConstraint("volume > 0", name="ck_signals_volume_positive"),
        CheckConstraint("max_deviation_points >= 0", name="ck_signals_deviation_nonnegative"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_signals_confidence_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    reference_price: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    point_size: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    max_deviation_points: Mapped[int] = mapped_column(Integer, nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    take_profit: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.8500")
    rationale: Mapped[dict[str, JSONValue]] = mapped_column(JSON, nullable=False, default=dict)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1.0-rule-based")
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="CREATED")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalEvent(Timestamped, Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint("signal_id", "to_state", name="uq_signal_events_transition"),
        Index("ix_signal_events_signal_created", "signal_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    signal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(500))
    execution_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    execution_volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, JSONValue] | None] = mapped_column(JSON)


class TradeReport(Timestamped, Base):
    __tablename__ = "trade_reports"
    __table_args__ = (
        UniqueConstraint("device_id", "external_order_id", name="uq_trade_reports_device_order"),
        Index("ix_trade_reports_user_closed", "user_id", "closed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    signal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL")
    )
    external_order_id: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    slippage_points: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    commission: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    swap: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_device_created", "device_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, JSONValue]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )