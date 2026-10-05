"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("risk_disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("two_factor_secret", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # User Sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_user_expires", "user_sessions", ["user_id", "expires_at"])

    # Pairing Codes
    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pairing_codes_code_hash", "pairing_codes", ["code_hash"], unique=True)
    op.create_index("ix_pairing_codes_user_expires", "pairing_codes", ["user_id", "expires_at"])
    op.create_index("ix_pairing_codes_expires", "pairing_codes", ["expires_at"])

    # Devices (EA Terminals)
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), server_default="MT5 Terminal", nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_build", sa.String(32), nullable=True),
        sa.Column("broker", sa.String(120), nullable=False),
        sa.Column("server", sa.String(120), nullable=False),
        sa.Column("account_number_masked", sa.String(64), nullable=False),
        sa.Column("account_currency", sa.String(8), nullable=False),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_devices_status"),
        sa.CheckConstraint("leverage >= 1", name="ck_devices_leverage_positive"),
    )
    op.create_index("ix_devices_token_hash", "devices", ["token_hash"], unique=True)
    op.create_index("ix_devices_user_status_last_seen", "devices", ["user_id", "status", "last_seen_at"])

    # Account Snapshots
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("margin", sa.Numeric(24, 8), server_default="0", nullable=False),
        sa.Column("free_margin", sa.Numeric(24, 8), nullable=False),
        sa.Column("margin_level", sa.Numeric(12, 4), nullable=True),
        sa.Column("open_positions_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("account_currency", sa.String(8), nullable=False),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_account_snapshots_balance_nonnegative"),
        sa.CheckConstraint("equity >= 0", name="ck_account_snapshots_equity_nonnegative"),
        sa.CheckConstraint("free_margin >= 0", name="ck_account_snapshots_margin_nonnegative"),
    )
    op.create_index("ix_account_snapshots_device_captured", "account_snapshots", ["device_id", "captured_at"])

    # Positions
    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_position_id", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("current_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("stop_loss", sa.Numeric(28, 12), nullable=True),
        sa.Column("take_profit", sa.Numeric(28, 12), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False),
        sa.Column("swap", sa.Numeric(24, 8), server_default="0", nullable=False),
        sa.Column("magic_number", sa.Integer(), nullable=True),
        sa.Column("comment", sa.String(120), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_open", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("device_id", "external_position_id", name="uq_positions_device_external"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_positions_side"),
        sa.CheckConstraint("volume > 0", name="ck_positions_volume_positive"),
    )
    op.create_index("ix_positions_device_open_observed", "positions", ["device_id", "is_open", "observed_at"])

    # Risk Profiles
    op.create_table(
        "risk_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_per_trade_pct", sa.Numeric(8, 4), server_default="0.5000", nullable=False),
        sa.Column("max_daily_loss_pct", sa.Numeric(8, 4), server_default="2.0000", nullable=False),
        sa.Column("max_open_risk_pct", sa.Numeric(8, 4), server_default="3.0000", nullable=False),
        sa.Column("max_open_positions", sa.Integer(), server_default="5", nullable=False),
        sa.Column("allowed_symbols", sa.JSON(), nullable=True),
        sa.Column("trading_hours", sa.JSON(), nullable=True),
        sa.Column("auto_execute", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("device_id", name="uq_risk_profiles_device"),
        sa.CheckConstraint("risk_per_trade_pct > 0 AND risk_per_trade_pct <= 5", name="ck_risk_profiles_trade_risk"),
        sa.CheckConstraint("max_daily_loss_pct > 0 AND max_daily_loss_pct <= 100", name="ck_risk_profiles_daily_loss"),
        sa.CheckConstraint("max_open_risk_pct > 0 AND max_open_risk_pct <= 100", name="ck_risk_profiles_open_risk"),
        sa.CheckConstraint("max_open_positions >= 1 AND max_open_positions <= 50", name="ck_risk_profiles_max_positions"),
    )

    # Signals
    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("reference_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("point_size", sa.Numeric(20, 12), nullable=False),
        sa.Column("max_deviation_points", sa.Integer(), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8), nullable=False),
        sa.Column("stop_loss", sa.Numeric(28, 12), nullable=False),
        sa.Column("take_profit", sa.Numeric(28, 12), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), server_default="0.8500", nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(64), server_default="v1.0-rule-based", nullable=False),
        sa.Column("state", sa.String(16), server_default="CREATED", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('BUY', 'SELL')", name="ck_signals_action"),
        sa.CheckConstraint("state IN ('CREATED', 'DELIVERED', 'ACKED', 'EXECUTED', 'REJECTED', 'EXPIRED')", name="ck_signals_state"),
        sa.CheckConstraint("volume > 0", name="ck_signals_volume_positive"),
        sa.CheckConstraint("max_deviation_points >= 0", name="ck_signals_deviation_nonnegative"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_signals_confidence_range"),
    )
    op.create_index("ix_signals_device_state_expires", "signals", ["device_id", "state", "expires_at"])

    # Signal Events
    op.create_table(
        "signal_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("signal_id", sa.Uuid(as_uuid=True), sa.ForeignKey("signals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state", sa.String(16), nullable=True),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("execution_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("execution_volume", sa.Numeric(20, 8), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("signal_id", "to_state", name="uq_signal_events_transition"),
    )
    op.create_index("ix_signal_events_signal_created", "signal_events", ["signal_id", "created_at"])

    # Trade Reports
    op.create_table(
        "trade_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_id", sa.Uuid(as_uuid=True), sa.ForeignKey("signals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_order_id", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("exit_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("slippage_points", sa.Numeric(12, 4), nullable=True),
        sa.Column("commission", sa.Numeric(24, 8), server_default="0", nullable=False),
        sa.Column("swap", sa.Numeric(24, 8), server_default="0", nullable=False),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("device_id", "external_order_id", name="uq_trade_reports_device_order"),
    )
    op.create_index("ix_trade_reports_user_closed", "trade_reports", ["user_id", "closed_at"])

    # Audit Logs (Append-Only)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_logs_device_created", "audit_logs", ["device_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("trade_reports")
    op.drop_table("signal_events")
    op.drop_table("signals")
    op.drop_table("risk_profiles")
    op.drop_table("positions")
    op.drop_table("account_snapshots")
    op.drop_table("devices")
    op.drop_table("pairing_codes")
    op.drop_table("user_sessions")
    op.drop_table("users")
