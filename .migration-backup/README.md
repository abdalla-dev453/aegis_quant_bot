# Aegis Quant

Onyx-fx is an AI-assisted MetaTrader 5 trading system with a Python execution service, a FastAPI monitoring/control API, a React dashboard, and two separate MQL5 EA sources.

> **Release status: NO-GO for funded/live trading.** The repository has no verified MetaEditor build, broker-connected qualification, signed risk approval, or supervised demo evidence. Follow the [production release checklist](PRODUCTION_RELEASE_CHECKLIST.md) before considering live use.

## What is implemented

- The Python runner evaluates configured symbols using closed-candle H1/H4 market data, requests schema-validated BUY/SELL/HOLD proposals from OpenAI, then applies deterministic signal and risk checks before entry.
- The default execution mode is `paper`. It performs analysis and order preflight checks and suppresses new entries and automatic trailing-stop changes. A user-confirmed close-positions request remains an explicit broker action in either mode.
- Risk and execution code includes broker-aware sizing, daily-loss and peak-drawdown guards, daily trade and concurrent-position limits, correlation checks, and trailing-stop management.
- The FastAPI service exposes account, risk, position, signal, order, log, and performance data to the dashboard. It also supports operator controls, credential setup, peak-guard reset, and confirmed closing of positions owned by this bot's magic number.
- The React dashboard polls the API and shows account/risk status, positions, signals, orders, logs, performance, and control state.
- `mt5/AegisConfluenceEA.mq5` is the preferred EA scaffold named by the release checklist. `AegisQuantEA.mq5` is a separate, smaller EA scaffold. They are independent execution paths, not the Python runner.

The manual-trading `DashboardTraderEA.mq5` described in an earlier draft is **not present** in this repository. Do not use that draft's installation steps or feature list for these sources.

## Immediate attention

The automatic mutation guards now skip trailing-stop updates in paper mode and when the operator control disallows management. `API_TOKEN` is required at startup in every mode, and the dashboard displays execution mode separately from operator control state. Dashboard re-arming after HALTED requires confirmation; direct authenticated API control changes remain an operator action.

**Live release gates remain open.** The release checklist identifies missing aggregate open-risk controls, durable loss-guard behavior, partial-fill/restart reconciliation, owner-approved limits, MetaEditor build evidence, Strategy Tester results, and supervised demo evidence. Unit tests and paper mode do not replace those gates.

Do not attach either EA or enable live orders on a funded account based on this README. The EAs and Python runner have different controls and must not be run together on the same account/symbol without an explicitly tested ownership plan.

## Architecture

| Path | Purpose |
| --- | --- |
| `server/main.py` | Async Python trading loop; starts the API and runs analysis/execution. |
| `server/ai_engine.py` | OpenAI proposal request, strict schema validation, fail-closed HOLD behavior. |
| `server/strategy.py` | Technical indicators and deterministic signal checks. |
| `server/execution.py` | Broker-aware order checks, order placement, risk guards, and trailing stops. |
| `server/news_provider.py` | MT5 calendar/news adapter with optional NewsAPI and Yahoo RSS fallbacks. |
| `server/api.py` | Authenticated FastAPI data and operator-control endpoints. |
| `client/` | React/Vite dashboard; API access is centralized in `src/lib/botFeed.js`. |
| `mt5/AegisConfluenceEA.mq5` | Preferred MQL5 confluence EA candidate; not compiled or broker-qualified here. |
| `AegisQuantEA.mq5` | Separate root-level EA scaffold. |
| `tests/` | Python regression/unit tests; not a profitability or broker-execution test suite. |

## Requirements

- Python 3.11 or newer and the dependencies in `server/requirements.txt`.
- A MetaTrader 5 terminal and broker session for account/market data. Native `MetaTrader5` Python support is Windows-only. Linux use requires a separately configured `mt5linux` bridge and `MT5LINUX_ENABLED=1`; that path must be qualified in its target environment.
- An OpenAI API key. The Python runner validates AI configuration at startup, including in paper mode.
- Node.js 20 or newer and npm for the React dashboard.
- MetaEditor on Windows to compile either `.mq5` source. No successful build is included in this repository.

## Local setup

Use a demo account. The backend starts its API and trading loop together.

1. Create and install the Python environment:

   ```powershell
   cd server
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

2. Edit `server/.env`. At minimum, set a non-empty API token, OpenAI key, paper mode, and local CORS origins:

   ```dotenv
   API_HOST=127.0.0.1
   API_PORT=8000
   CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
   API_TOKEN=<long-random-token>
   TRADING_MODE=paper
   OPENAI_API_KEY=<your-openai-key>
   OPENAI_MODEL=gpt-4o
   MT5_LOGIN=<demo-login>
   MT5_PASSWORD=<demo-password>
   MT5_SERVER=<demo-server>
   ```

   MT5 credentials may instead be entered through the dashboard Settings page after startup, but the API token is still required. Keep real values out of version control.

3. Start the Python service from the `server/` directory:

   ```powershell
   python main.py
   ```

   The API listens at `http://127.0.0.1:8000` by default. The health route is `/healthz`; protected API routes require the configured token.

4. In a second terminal, configure and start the dashboard:

   ```powershell
   cd client
   Copy-Item .env.example .env
   npm install
   npm run dev -- --host 127.0.0.1
   ```

   Set `VITE_API_BASE=http://127.0.0.1:8000` and `VITE_API_TOKEN` to the same value as `API_TOKEN`. The Vite token is included in the browser bundle; this setup is for local development, not a public deployment.

For Linux service setup, secrets, Nginx, health checks, and demo acceptance gates, see [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md). For MT5 and EA operating instructions, see [RUNNING_MT5_BOT.md](RUNNING_MT5_BOT.md).

## Configuration and behavior

- Default symbols are `EURUSD`, `GBPUSD`, and `XAUUSD`; risk, indicator, execution, and deployment settings are defined in `server/config.py` and can be overridden by supported environment variables.
- The AI response is constrained to BUY, SELL, or HOLD and validated before use. A malformed or unavailable AI response fails closed to HOLD. AI proposals do not bypass deterministic strategy, portfolio, broker, or execution checks.
- News context can come from an MT5 bridge, optional NewsAPI, or Yahoo RSS. Provider availability, event classification, freshness, and broker-time alignment must be verified for the deployment; this is not a guaranteed licensed economic-calendar feed.
- Dashboard positions and close actions are limited to positions tagged with the configured Python bot magic number. The close action sends broker market orders and can operate even when new entries are in paper mode; use its confirmation deliberately.
- Pause/HALT state, API connectivity, and `TRADING_MODE` are separate concepts. Do not infer live versus paper execution from the dashboard's RUNNING label.

## Verification

Run the Python tests from the repository root with the project environment active:

```bash
python -m pytest tests -q
```

Build and lint the client:

```bash
cd client
npm run build
npm run lint
```

These checks validate software behavior and packaging only. They do not establish strategy profitability, broker compatibility, safe live execution, or release approval.

## Related documentation

- [MT5 runbook](RUNNING_MT5_BOT.md)
- [Deployment guide](deploy/DEPLOYMENT.md)
- [Production release checklist](PRODUCTION_RELEASE_CHECKLIST.md)
- [Production readiness audit](PRODUCTION_READINESS_AUDIT.md)
- [Security notes](SECURITY.md)

Trading leveraged products can result in rapid losses. This software is not financial advice and makes no guarantee of performance. Use only supervised demo environments until every release gate has been independently verified and approved.