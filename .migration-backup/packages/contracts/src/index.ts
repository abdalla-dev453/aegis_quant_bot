/**
 * @aegis-quant/contracts
 * Single source of truth for API schemas, models, and shared contract constants.
 */

export * from "./generated.ts";

export const SIGNAL_ACTIONS = ["BUY", "SELL"] as const;
export const SIGNAL_STATES = [
  "CREATED",
  "DELIVERED",
  "ACKED",
  "EXECUTED",
  "REJECTED",
  "EXPIRED",
] as const;

export const DEVICE_PRESENCE = ["ONLINE", "STALE", "OFFLINE"] as const;

export const REASON_CODES = {
  TTL_EXPIRED: "TTL_EXPIRED",
  PRICE_DEVIATION: "PRICE_DEVIATION",
  SYMBOL_DISALLOWED: "SYMBOL_DISALLOWED",
  DAILY_LOSS_LIMIT_REACHED: "DAILY_LOSS_LIMIT_REACHED",
  MAX_POSITIONS_REACHED: "MAX_POSITIONS_REACHED",
  INSUFFICIENT_MARGIN: "INSUFFICIENT_MARGIN",
  BROKER_STOP_LEVEL_INVALID: "BROKER_STOP_LEVEL_INVALID",
  ORDER_SEND_FAILED: "ORDER_SEND_FAILED",
} as const;

export type ReasonCode = (typeof REASON_CODES)[keyof typeof REASON_CODES];

export function isSignalAction(value: unknown): value is import("./generated.js").SignalAction {
  return value === "BUY" || value === "SELL";
}

export function isSignalState(value: unknown): value is import("./generated.js").SignalState {
  return (
    typeof value === "string" &&
    (SIGNAL_STATES as readonly string[]).includes(value)
  );
}

export function formatPnl(amount: number | string, currency = "USD"): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  if (isNaN(num)) return `0.00 ${currency}`;
  const sign = num > 0 ? "+" : num < 0 ? "-" : "";
  const abs = Math.abs(num).toFixed(2);
  return `${sign}$${abs}`;
}
