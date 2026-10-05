/**
 * Canonical Generated API & Entity Schema Definitions
 * AegisQuant Engine Contract Types (OpenAPI 3.1)
 *
 * Single Source of Truth for Backend (FastAPI) and Frontend (Next.js)
 */

export type SignalAction = "BUY" | "SELL";

export type SignalState =
  | "CREATED"
  | "DELIVERED"
  | "ACKED"
  | "EXECUTED"
  | "REJECTED"
  | "EXPIRED";

export type DeviceStatus = "ACTIVE" | "REVOKED";

export type DevicePresence = "ONLINE" | "STALE" | "OFFLINE";

export interface ErrorResponse {
  code: string;
  message: string;
  details?: Record<string, string | number | boolean | null> | null;
}

export interface UserView {
  id: string;
  email: string;
  is_verified: boolean;
  risk_disclaimer_accepted_at: string;
  created_at: string;
}

export interface UserSignup {
  email: string;
  password: string;
  risk_disclaimer_accepted: boolean;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface PairingCodeView {
  code: string;
  expires_at: string;
}

export interface EAPairRequest {
  code: string;
  terminal_build: string;
  broker: string;
  server: string;
  account_number_masked: string;
  account_currency: string;
  leverage: number;
}

export interface EAPairResponse {
  device_id: string;
  device_token: string;
  token_type: string;
  token_shown_once: boolean;
}

export interface AccountSnapshotInput {
  balance: string;
  equity: string;
  margin?: string;
  free_margin: string;
  margin_level?: string | null;
  open_positions_count?: number;
  account_currency: string;
  leverage: number;
  captured_at: string;
}

export interface PositionInput {
  external_position_id: string;
  symbol: string;
  side: SignalAction;
  volume: string;
  entry_price: string;
  current_price: string;
  stop_loss?: string | null;
  take_profit?: string | null;
  unrealized_pnl: string;
  swap?: string;
  magic_number?: number | null;
  comment?: string | null;
  observed_at: string;
}

export interface HeartbeatRequest {
  snapshot: AccountSnapshotInput;
  positions: PositionInput[];
}

export interface HeartbeatResponse {
  accepted: boolean;
  server_time: string;
  auto_execute: boolean;
  kill_switch: boolean;
}

export interface SignalRationaleFactor {
  name: string;
  weight: string;
  description: string;
}

export interface SignalRationale {
  summary: string;
  factors: SignalRationaleFactor[];
}

export interface SignalDelivery {
  signal_id: string;
  symbol: string;
  action: SignalAction;
  reference_price: string;
  point_size: string;
  max_deviation_points: number;
  volume: string;
  stop_loss: string;
  take_profit: string;
  confidence: string;
  rationale: SignalRationale;
  model_version: string;
  expires_at: string;
  auto_execute: boolean;
}

export interface SignalAckRequest {
  event: "ACKED" | "EXECUTED" | "REJECTED";
  occurred_at: string;
  execution_price?: string | null;
  execution_volume?: string | null;
  reason_code?: string | null;
  reason?: string | null;
}

export interface SignalAckResponse {
  signal_id: string;
  state: SignalState;
  accepted: boolean;
}

export interface SignalView {
  id: string;
  device_id: string;
  symbol: string;
  action: SignalAction;
  reference_price: string;
  volume: string;
  stop_loss: string;
  take_profit: string;
  confidence: string;
  rationale: SignalRationale;
  model_version: string;
  state: SignalState;
  expires_at: string;
  created_at: string;
}

export interface SignalEventView {
  id: string;
  signal_id: string;
  device_id: string;
  from_state?: string | null;
  to_state: string;
  source: string;
  reason_code?: string | null;
  reason?: string | null;
  execution_price?: string | null;
  execution_volume?: string | null;
  occurred_at: string;
}

export interface RiskProfileView {
  id: string;
  device_id: string;
  risk_per_trade_pct: string;
  max_daily_loss_pct: string;
  max_open_risk_pct: string;
  max_open_positions: number;
  allowed_symbols?: string[] | null;
  trading_hours?: Record<string, string | number | boolean | null> | null;
  auto_execute: boolean;
}

export interface RiskProfileUpdate {
  risk_per_trade_pct?: string;
  max_daily_loss_pct?: string;
  max_open_risk_pct?: string;
  max_open_positions?: number;
  allowed_symbols?: string[];
  trading_hours?: Record<string, string | number | boolean | null>;
  auto_execute?: boolean;
}

export interface DeviceView {
  id: string;
  name: string;
  broker: string;
  server: string;
  terminal_build?: string | null;
  account_number_masked: string;
  account_currency: string;
  leverage: number;
  status: string;
  presence: DevicePresence;
  last_seen_at?: string | null;
  auto_execute: boolean;
  created_at: string;
}

export interface DeviceRename {
  name: string;
}

export interface TradeReportInput {
  signal_id?: string | null;
  ticket: string;
  symbol: string;
  side: SignalAction;
  volume: string;
  execution_price: string;
  exit_price?: string | null;
  slippage_points?: string | null;
  commission?: string;
  swap?: string;
  profit?: string | null;
  opened_at: string;
  closed_at?: string | null;
}

export interface TradeReportView {
  id: string;
  signal_id?: string | null;
  device_id: string;
  ticket: string;
  symbol: string;
  side: SignalAction;
  volume: string;
  execution_price: string;
  exit_price?: string | null;
  slippage_points?: string | null;
  commission: string;
  swap: string;
  realized_pnl?: string | null;
  opened_at: string;
  closed_at?: string | null;
  created_at: string;
}

export interface AuditLogView {
  id: string;
  user_id?: string | null;
  device_id?: string | null;
  event_type: string;
  action?: string | null;
  request_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  details: Record<string, string | number | boolean | null>;
  created_at: string;
}

export interface DashboardAccount {
  device_id: string;
  captured_at: string;
  balance: string;
  equity: string;
  margin: string;
  free_margin: string;
  margin_level?: string | null;
  open_positions_count: number;
  account_currency: string;
}

export interface DashboardPosition {
  device_id: string;
  external_position_id: string;
  symbol: string;
  side: SignalAction;
  volume: string;
  entry_price: string;
  current_price: string;
  stop_loss?: string | null;
  take_profit?: string | null;
  unrealized_pnl: string;
  observed_at: string;
}

export interface DashboardResponse {
  devices: DeviceView[];
  accounts: DashboardAccount[];
  positions: DashboardPosition[];
}
