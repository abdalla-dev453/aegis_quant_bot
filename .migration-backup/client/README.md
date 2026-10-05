# Aegis Quant Dashboard

React, Vite, and Tailwind client for the Aegis Quant FastAPI service. The client
uses live API responses; it does not generate mock trading data.

## Run locally

1. Start the Python service by following the root [README](../README.md). It
   starts the API on port 8000 by default.
2. Copy `.env.example` to `.env` and set:

   ```dotenv
   VITE_API_BASE=http://127.0.0.1:8000
   VITE_API_TOKEN=<same-non-empty-token-as-server>
   ```

   The API currently requires a non-empty token for protected routes, including
   local and paper-mode requests. Configure the same value as `API_TOKEN` in
   `server/.env`.
3. Install and run:

   ```bash
   npm install
   npm run dev -- --host 127.0.0.1
   ```

## Views and controls

- **Dashboard:** account and risk metrics, latest signal/order/event, market
  chart, confluence, calendar/news, positions, execution log, and proposals.
- **Performance Matrix:** historical equity curve, trade distribution, and
  performance summaries from the API.
- **Logs:** API-provided bot log entries.
- **Settings:** bot configuration and MT5 credential workflow.
- **Strategy Builder:** displays server settings and validates a local parameter
  draft; it does not save changes to the running bot.

The dashboard can pause/resume entries and request an emergency halt. Its
close-positions action is confirmed and scoped to positions matching the
Python bot's configured magic number. The API action is a real broker action,
not a simulation.

## Important security and mode notes

- `VITE_API_TOKEN` is compiled into the frontend bundle. Treat it as visible to
  browser users; use a private deployment, TLS, and an access-controlled
  gateway rather than treating this token as a user identity boundary.
- `TRADING_MODE=paper` suppresses new entry orders and automatic trailing-stop
  modifications. The explicit close-position action still submits broker
  market orders, including in paper mode.
- Execution mode is displayed separately from the operator control state. The
  dashboard requires confirmation to re-arm HALTED; direct authenticated API
  control changes remain an operator action.

Run `npm run build` and `npm run lint` from this directory. See the root
[README](../README.md) and [deployment guide](../deploy/DEPLOYMENT.md) for
backend setup and release requirements.
