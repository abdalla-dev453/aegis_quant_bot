# AegisQuant MT5 Bridge Expert Advisor (`AegisQuantEA.mq5`)

## Overview
`AegisQuantEA.mq5` is a production-grade MetaTrader 5 Expert Advisor that securely connects an MT5 client terminal to the AegisQuant Cloud Backend over an HMAC-SHA256 authenticated HTTPS bridge.

### Core Architectural Invariants
1. **Zero Credential Sharing**: MT5 account credentials and master/investor passwords never leave the local terminal.
2. **Local Risk Enforcement**: The EA acts as the final gatekeeper. Even if a signal passes backend risk validation, the EA evaluates local tick spread, margin, daily loss limit, broker stop level, and price deviation before order dispatch.
3. **Idempotent Signal Execution**: Every signal contains a unique UUIDv7 identifier that is injected into the MT5 order comment (`AQ:<UUID>`). On initialization or reconnect, active and historical tickets are scanned to guarantee zero duplicate trades across restarts.
4. **Resilient Non-Blocking Polling**: MT5's `WebRequest()` is synchronous and blocking. Polling is executed strictly with a maximum 3000 ms timeout on timer intervals, featuring exponential backoff ($1\text{s}, 2\text{s}, 4\text{s} \dots 60\text{s}$) when the cloud is offline.

---

## Setup & MT5 Configuration

### 1. Whitelist Backend URL
In MetaTrader 5:
1. Navigate to **Tools** -> **Options** -> **Expert Advisors**.
2. Check **Allow WebRequest for listed URL**.
3. Add your AegisQuant API endpoint:
   - Development: `http://127.0.0.1:8000`
   - Production: `https://api.aegisquant.com`
4. Check **Allow algorithmic trading**.

### 2. Pairing with AegisQuant Cloud
1. In the AegisQuant Web Dashboard, navigate to **Devices** -> **Pair New Terminal**.
2. Copy the single-use 8-character pairing code (e.g. `AQ-8X9K2P`).
3. Attach `AegisQuantEA` to any chart (e.g. `EURUSD` M1).
4. In the inputs dialog:
   - `InpServerUrl`: `https://api.aegisquant.com`
   - `InpPairingCode`: Enter the 8-character pairing code.
5. On the first execution tick, the EA exchanges the pairing code via `POST /ea/v1/pair` for a unique 256-bit `deviceToken` + HMAC secret.
6. The credentials are encrypted and stored locally in the terminal sandbox at `MQL5/Files/aegis_quant_device.dat`. Credentials are **never** written to terminal logs.
7. Subsequent EA runs read the persisted device credentials and begin heartbeat streaming.

---

## Input Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `InpServerUrl` | `string` | `"http://127.0.0.1:8000"` | HTTPS base URL of the AegisQuant backend |
| `InpPairingCode` | `string` | `""` | Single-use 8-character pairing code |
| `InpHeartbeatSec` | `int` | `5` | Heartbeat & snapshot broadcast interval (seconds) |
| `InpSignalPollSec` | `int` | `1` | Signal queue polling interval (seconds) |
| `InpMaxSignalDeviationPts` | `int` | `30` | Maximum allowable price deviation in points |
| `InpMaxDailyLossPct` | `double` | `2.0` | Maximum daily loss tolerance before EA pause |
| `InpMaxOpenPositions` | `int` | `5` | Maximum concurrent open positions on account |

---

## Signal Execution & Rejection Codes

When the EA evaluates a signal, it executes a strict 8-step pipeline:
1. `TTL_EXPIRED`: Signal timestamp exceeds TTL (stale signal).
2. `PRICE_DEVIATION`: Market price drifted past `maxDeviationPoints` from reference price.
3. `SYMBOL_DISALLOWED`: Symbol is not in allowed instrument list.
4. `DAILY_LOSS_LIMIT_REACHED`: Cumulative daily loss exceeded configured risk ceiling.
5. `MAX_POSITIONS_REACHED`: Terminal already has maximum open positions.
6. `INSUFFICIENT_MARGIN`: Free margin check failed for requested volume.
7. `BROKER_STOP_LEVEL_INVALID`: SL/TP is closer to current price than broker minimum stop level.
8. `ORDER_SEND_FAILED`: MT5 trade server returned an execution error.

If rejected, the EA posts `POST /ea/v1/signals/:id/ack` with status `REJECTED` and the specific reason code.
