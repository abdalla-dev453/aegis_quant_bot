# ADR 004: Dual-Layer Risk Enforcement Architecture

## Status
Accepted

## Context
Automated algorithmic trading systems face catastrophic loss risks if risk controls fail or if network disconnects prevent backend orders from being cancelled.

Relying solely on server-side risk checks is dangerous if the client terminal's equity changes rapidly (e.g. manual trades, floating drawdown). Conversely, relying solely on client-side checks leaves no centralized circuit breaker or kill switch.

## Decision
We mandate a **Dual-Layer Risk Architecture**: Risk controls are evaluated on the backend AND independently evaluated on the local MT5 EA terminal. The local EA holds ultimate veto power.

### Layer 1: Backend Pre-Trade Validation
Before a signal is queued for delivery to a device:
1. **Account Limits**: Verifies current reported daily loss $< \text{maxDailyLossPct}$.
2. **Open Exposure**: Verifies current open risk $< \text{maxOpenRiskPct}$ and open positions $< \text{maxOpenPositions}$.
3. **Trading Hours & Symbols**: Verifies active trading window and permitted instrument universe.
4. **Auto-Execute Authority**: Verifies user has explicitly enabled `auto_execute = true` on the account.

### Layer 2: Local EA Terminal Final Gatekeeper
Before the EA submits `OrderSend()` to the broker trade server:
1. **Live Margin Check**: Calls `OrderCalcMargin()` with live ask/bid tick data to ensure sufficient free margin.
2. **Daily Loss Ceiling**: Aggregates realized + unrealized PnL from midnight terminal time. If loss $\ge \text{InpMaxDailyLossPct}$, execution is halted.
3. **Broker Stop Level Check**: Verifies SL and TP distance $\ge \text{SYMBOL_TRADE_STOPS_LEVEL}$ to avoid broker execution rejection.
4. **Lot Sizing & Tick Rounding**: Rounds lot size strictly to `SYMBOL_VOLUME_STEP` between `SYMBOL_VOLUME_MIN` and `SYMBOL_VOLUME_MAX`. Rounds prices to `SYMBOL_TICK_SIZE`.
5. **Local AI Auto Toggle**: The UI panel includes a physical "AI Auto" switch. If turned off locally, signal auto-execution is vetoed regardless of backend settings (stricter setting wins).

### Emergency Kill-Switch Protocol
- When the user triggers the Kill Switch via web UI or EA panel:
  1. Backend publishes immediate emergency event over Redis & sets `kill_switch_active = true`.
  2. On the next heartbeat response (or immediate panel trigger), the EA immediately flattens all open positions and cancels pending orders.
  3. Auto-execution is latched to `false` and requires explicit manual reenabling.

## Rejected Alternatives
1. **Server-Only Risk Engine**:
   - *Rejected* because stale telemetry between heartbeats could lead to margin calls on volatile markets.
2. **Client-Only Risk Engine**:
   - *Rejected* because it eliminates centralized risk management across multiple terminals and disables backend kill-switch propagation.

## Consequences
- **Positive**: Defense-in-depth ensures that neither server bugs nor terminal sync delays can breach risk constraints.
- **Negative**: Redundant risk calculation requires maintaining consistent mathematical definitions in both Python and MQL5.
