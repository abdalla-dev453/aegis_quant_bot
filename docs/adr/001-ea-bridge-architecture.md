# ADR 001: EA Bridge Communication Protocol (HTTPS Polling vs WebSockets in MQL5)

## Status
Accepted

## Context
The AegisQuant platform connects MetaTrader 5 (MT5) terminals running Expert Advisors (EAs) with a cloud backend that distributes AI-generated trading signals and aggregates real-time account telemetry.

MetaTrader 5 provides native network communication via the `WebRequest()` MQL5 function. However:
1. `WebRequest()` is strictly blocking and synchronous.
2. MQL5 does not provide native, stable WebSocket support without loading third-party DLLs.
3. Loading third-party DLLs in MT5 exposes users to security risks, disables MT5 marketplace compliance, requires administrative permissions, and complicates user installation.
4. If a network call hangs, the EA thread in MT5 freezes unless bounded by a strict timeout.

## Decision
We adopt an **HTTPS REST + Short Long-Poll Bridge** utilizing MT5's native `WebRequest()`:
1. **Heartbeat & Telemetry (`POST /ea/v1/heartbeat`)**:
   - Sent on a periodic timer (default 5 seconds).
   - Reports current balance, equity, free margin, and active open positions.
   - Server returns current server time, config updates, and emergency kill-switch status.
2. **Signal Polling (`GET /ea/v1/signals?since=cursor`)**:
   - Polled on a dedicated timer loop (1–2 seconds) with a server-side short timeout (or immediate queue drain).
   - Strict 3000 ms timeout on every `WebRequest()` call.
3. **Exponential Backoff**:
   - If the backend is unreachable or returns 5xx errors, the EA backs off ($1\text{s}, 2\text{s}, 4\text{s} \dots 60\text{s}$) while keeping the local UI and stop-loss management fully operational.
4. **Dual API Surfaces**:
   - `/ea/v1/*`: Terminal device endpoints (authenticated via HMAC-SHA256).
   - `/app/v1/*`: Web user endpoints (authenticated via HTTP-only secure cookie sessions).
   - Server-sent events (SSE) / WebSockets fed by Redis Pub/Sub are used exclusively between the backend and the Next.js web application frontend.

## Rejected Alternatives
1. **MQL5 DLL with WebSockets**:
   - *Rejected* because requiring users to enable DLL imports breaks trust, fails MT5 security audits, and introduces crash vulnerabilities in the terminal process.
2. **Local Python Sidecar on User Machine**:
   - *Rejected* for the primary user experience due to installation friction (Python runtime, pip dependencies, OS permissions). The standalone MQL5 single-file EA is zero-friction.

## Consequences
- **Positive**: Native MT5 compatibility with zero external DLL dependencies; clean separation between high-frequency EA communication and user web sessions; deterministic failure recovery.
- **Negative**: Adds minor latency overhead (tens of milliseconds) compared to raw TCP sockets, which is negligible for swing and multi-minute intraday AI trade signals.
