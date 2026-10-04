import {
  DEVICE_PRESENCE,
  formatPnl,
  isSignalAction,
  isSignalState,
  REASON_CODES,
  SIGNAL_ACTIONS,
  SIGNAL_STATES,
} from "./index.ts";

// Test Type and Helper Guards
if (!isSignalAction("BUY")) {
  throw new Error("isSignalAction failed for BUY");
}
if (!isSignalAction("SELL")) {
  throw new Error("isSignalAction failed for SELL");
}
if (isSignalAction("INVALID")) {
  throw new Error("isSignalAction allowed invalid value");
}

if (!isSignalState("CREATED")) {
  throw new Error("isSignalState failed for CREATED");
}
if (!isSignalState("EXECUTED")) {
  throw new Error("isSignalState failed for EXECUTED");
}
if (isSignalState("UNKNOWN")) {
  throw new Error("isSignalState allowed unknown state");
}

if (formatPnl("150.25") !== "+$150.25") {
  throw new Error(`formatPnl positive mismatch: ${formatPnl("150.25")}`);
}
if (formatPnl("-42.50") !== "-$42.50") {
  throw new Error(`formatPnl negative mismatch: ${formatPnl("-42.50")}`);
}

console.log("All contract assertions passed successfully.");
