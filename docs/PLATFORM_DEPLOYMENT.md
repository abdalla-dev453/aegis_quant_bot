# Hosted dashboard and MT5 deployment

**Current status: deployable hosting configuration; not a live-trading release.** This repository has separate components that must not be confused:

| Component | Suitable host | What it does |
| --- | --- | --- |
| React/Vite dashboard (`artifacts/onyx-fx`) | Vercel or Netlify | Static UI only; browser calls the API over HTTPS. |
| EA bridge API (`lib/ea-bridge`) | Railway or Render | User/device auth, telemetry, database and Redis-backed replay/rate limiting. |
| MT5 terminal and preferred EA (`mt5/AegisConfluenceEA.mq5`) | Windows VPS with desktop MT5 | Broker connection and EA execution. |
| Python execution engine (`lib/trading-engine`) | Windows VPS with MT5 terminal | Uses the MetaTrader5 Python package and terminal IPC; it is not a Railway/Render Linux worker. |

The EA bridge's signal dispatch intentionally returns `503 signal_engine_unavailable` until a qualified signal engine and timestamped market-data path are implemented. Deploying the dashboard and API does **not** make automated BUY/SELL execution available. The Python execution engine can make deterministic directional proposals, but remains a separate runtime and has not been broker-qualified.

## Recommended split

Use a custom domain with two subdomains under the same registrable domain, for example `app.example.com` and `api.example.com`. The bridge sets an HTTP-only `SameSite=Strict` session cookie and the browser uses credentialed CORS. Separate provider domains such as `something.vercel.app` and `something.onrender.com` are cross-site and will not work reliably with that cookie policy.

Keep the API, database and Redis private where the host supports private networking. Only the API HTTPS endpoint and static dashboard need public web access. Keep the MT5 machine on Windows, connect it outbound to the API over HTTPS, and add the API host to MT5's allowed WebRequest URLs. Do not expose RDP or database/Redis ports publicly.

## 1. Deploy the bridge API on Render

Create a Render Blueprint or configure the service in the dashboard:

1. Create a PostgreSQL database and a Key Value (Redis-compatible) service in the same region as the API. Use a plan with the persistence and uptime needed for production; an ephemeral or sleeping cache is unsuitable for replay protection and rate limiting.
2. Create a Python Web Service from this repository. Set **Root Directory** to `lib/ea-bridge`.
3. Configure:
   - Build command: `pip install .`
   - Pre-deploy command: `alembic upgrade head`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/readyz`
4. Set service environment variables:
   - `APP_ENV=production`
   - `WEB_ORIGIN=https://app.example.com`
   - `SESSION_COOKIE_SECURE=true`
   - `DATABASE_URL` from the Render PostgreSQL **internal** connection string.
   - `REDIS_URL` from the Render Key Value **internal** connection string. Keep API, Postgres and Key Value in the same region.
5. Attach `api.example.com` as a custom domain and wait for HTTPS to be active. Do not put database or Redis credentials in the frontend or source control.

The app normalizes the platform's `postgres://` or `postgresql://` connection string to SQLAlchemy's asyncpg driver URL. `/readyz` checks both Postgres and Redis; `/healthz` is only a process liveness response. The secure production settings reject a non-HTTPS browser origin or disabled secure cookies.

## 2. Or deploy the bridge API on Railway

1. Create a Railway project with a Postgres service, a Redis service, and an API service from the repository.
2. Set the API service **Root Directory** to `/lib/ea-bridge` (Railway may display this as `lib/ea-bridge`).
3. Configure build command `pip install .` and start command:

   ```sh
   alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
   ```

   Run one API replica while migrations execute at start. For multi-replica production, run migrations once as a release/deploy step before scaling the API.
4. Add variables to the API service:
   - `APP_ENV=production`
   - `WEB_ORIGIN=https://app.example.com`
   - `SESSION_COOKIE_SECURE=true`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `REDIS_URL=${{Redis.REDIS_URL}}` (use the exact service variable name Railway exposes)
5. Set the service health-check path to `/readyz`, attach `api.example.com`, and keep Postgres and Redis without public domains. Use Railway private networking for their connections.

If the Railway Postgres service exposes a plain `postgresql://` URL, the app converts it to asyncpg form at startup. Confirm the variable reference resolves before the first deploy.

## 3. Deploy the dashboard to Vercel

The repository includes a root [`vercel.json`](../vercel.json) for the monorepo build. Import the repository with the project root left at the repository root, not `artifacts/onyx-fx` (the dashboard depends on workspace packages outside that directory).

The config runs `pnpm install --frozen-lockfile`, builds `@workspace/onyx-fx`, and publishes `artifacts/onyx-fx/dist/public`. Add this **public, non-secret** build variable in Vercel Production and Preview environments:

```text
VITE_API_URL=https://api.example.com/app/v1
```

Attach `app.example.com`, then set the bridge's `WEB_ORIGIN` to that exact origin. Vite now defaults `PORT` to `5173` and `BASE_PATH` to `/`, so static builds do not require hosting-specific values. Vite `VITE_*` values are compiled into browser assets; never put credentials or API secrets in them.

## 4. Or deploy the dashboard to Netlify

The root [`netlify.toml`](../netlify.toml) sets the pnpm monorepo build, publish directory, Vite variables, and SPA history fallback. In Netlify, select the repository root as the base/package directory and add the same public build variable:

```text
VITE_API_URL=https://api.example.com/app/v1
```

Attach `app.example.com`, then make the bridge `WEB_ORIGIN` match exactly. Trigger a new build after changing `VITE_API_URL`; it is a build-time value.

## 5. Run MT5 on Windows

1. Provision a supported Windows VPS and install the broker's MetaTrader 5 terminal. Keep the terminal, EA and broker account on the same Windows machine.
2. Compile `mt5/AegisConfluenceEA.mq5` in the target broker's MetaEditor, resolve all compiler errors, then install the resulting EA in that terminal. Compilation has not yet been verified from this repository.
3. Start with a broker demo account. Configure the EA's expected login, server and margin mode exactly; keep `InpAllowRealAccount=false`.
4. In MT5, allow outbound WebRequest to `https://api.example.com` only if using the bridge EA client. Protect the device-pairing secret and never place it in screenshots or logs.
5. Observe the terminal and API logs, verify heartbeat and position reconciliation, and exercise pause/kill/restart recovery. The current bridge dispatch remains disabled, so this setup only provides the bridge's currently implemented functionality; it does not authorize its generated signals to trade.

For the Python execution engine instead, install and run `lib/trading-engine` on Windows beside the MT5 terminal using its `.env.example`, with `TRADING_MODE=paper` and its local control API private behind an authenticated reverse proxy. Do not publish its shared `API_TOKEN` in a Vite variable. A Linux web-service deployment is not a substitute for Windows MT5 terminal IPC.

## Go-live gates

The platform setup is ready only when the deployment is reachable, `/readyz` passes with database and Redis available, migrations are current, browser login works on the custom domain, the MT5 demo terminal heartbeats correctly, and logs/backup/restart/kill procedures have been rehearsed. Before funded trading, separately require a successful EA compile, broker-specific demo qualification, exact order/deal/position reconciliation, historical backtest and out-of-sample reports, security review, and owner approval. The current release checklist remains **NO-GO for live trading**.
