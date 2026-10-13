# AegisQuant — Full Deployment Guide (Vercel + Render)

This guide covers deploying the complete AegisQuant stack now that the dashboard
is already on Vercel.

## Architecture overview

| Piece                                  | Runs on                              | Repo path                                           | Notes                                                           |
| -------------------------------------- | ------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------- |
| Dashboard (web)                        | ✅ Vercel (done)                     | `artifacts/onyx-fx` (built as `@workspace/onyx-fx`) | Static SPA, rewrites to `index.html`                            |
| FastAPI backend (EA bridge + user API) | Render Web Service                   | `lib/ea-bridge` (`app.main:app`)                    | Serves `/app/v1/*` and `/ea/v1/*`                               |
| Postgres                               | Render Postgres                      | —                                                   | `DATABASE_URL`                                                  |
| Redis                                  | Render Redis                         | —                                                   | `REDIS_URL` (sessions, cache, rate limits)                      |
| Migrations                             | `preDeployCommand` (`alembic upgrade head`) | `lib/ea-bridge/alembic`                             | Runs automatically before each deploy           |
| MT5 terminal + EA                      | **Windows VPS** (NOT Render/Railway) | `AegisQuantEA.mq5`, `server/mt5setup.exe`           | MT5 is Windows-only; the VPS calls OUT to the Render bridge URL |

> ⚠️ Do **not** try to host MT5 on Render or Railway. They are Linux hosts
> without a GUI — MetaTrader 5 will not run there. A cheap Windows VPS
> (Contabo, Vultr, AWS Lightsail Windows, ForexVPS) is the standard approach.

---

## 1. Deploy the backend on Render (Blueprint, one click)

A `render.yaml` blueprint is included at the repo root. It provisions
Postgres + Key Value (Redis) + the FastAPI web service (with auto-migrations on deploy).

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo. Render reads `render.yaml`.
3. It will ask for one manual value:
   - `WEB_ORIGIN` → your Vercel dashboard URL, e.g. `https://aegis-quant.vercel.app`
     (exact origin — scheme + host only, **no trailing slash, no path**).
4. Deploy. Render auto-generates `API_TOKEN` (view/copy it under the service's
   Environment tab — you'll need it for the EA).

Render URLs will be like `https://aegis-api-xxxx.onrender.com`.
Health checks: `GET /healthz` (liveness) and `GET /readyz` (checks Postgres + Redis).

### Manual alternative (no blueprint)

New → Web Service:

- **Runtime:** Docker (uses `lib/ea-bridge/Dockerfile`) — or Python 3.12 with
  build `pip install .` and start command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
- **Root directory:** `lib/ea-bridge`
- Then add Postgres and Redis add-ons (New → Postgres / Redis) and wire the URLs.

---

## 2. Environment variables (Render → service → Environment)

| Variable                | Value                                                                 | Why                                                                |
| ----------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `APP_ENV`               | `production`                                                          | Enables secure-cookie/HTTPS validation                             |
| `WEB_ORIGIN`            | `https://<your-vercel-app>.vercel.app`                                | The ONLY allowed CORS origin; must be HTTPS in production          |
| `DATABASE_URL`          | from the Render Postgres `connectionString` (auto-wired by blueprint) | App rewrites `postgres://` → `postgresql+asyncpg://` automatically |
| `REDIS_URL`             | from the Render Redis instance (auto-wired)                           | Sessions/cache/pubsub                                              |
| `SESSION_COOKIE_SECURE` | `true`                                                                | Required in production; login cookie is `SameSite=Strict`          |
| `API_TOKEN`             | long random string (`openssl rand -hex 32`)                           | Guards protected routes; same token goes into the EA               |

Optional (EA-bridge tuning, defaults are sane):
`SESSION_TTL_SECONDS`, `PAIRING_CODE_TTL_SECONDS`, `SIGNAL_TTL_SECONDS`,
`REQUEST_MAX_AGE_SECONDS`, `NONCE_TTL_SECONDS`, `EA_RATE_LIMIT_PER_MINUTE`,
`APP_RATE_LIMIT_PER_MINUTE`.

### Optional: the legacy MT5 monitor API (`lib/trading-engine/api.py`)

If you also deploy the older read-only dashboard bridge, it needs:

- `API_TOKEN` (**mandatory** — it refuses to start without it)
- `CORS_ORIGINS` → comma-separated absolute origins, e.g.
  `https://aegis-quant.vercel.app` — no `*`, no trailing slash
- `OPENAI_API_KEY` (required by its AI config)
- `TRADING_MODE`, `API_HOST`, `API_PORT`, `MAX_CANDLE_AGE_SECONDS`

---

## 3. Vercel (dashboard) variables

In Vercel → Project → Settings → Environment Variables:

| Variable       | Value                             |
| -------------- | --------------------------------- |
| `VITE_API_URL` | `https://<render-api-url>/app/v1` |

`artifacts/onyx-fx/src/lib/api.js` reads `VITE_API_URL` and falls back to
`/app/v1` (same-origin). Because the app sends `credentials: "include"` and the
session cookie is `SameSite=Strict`, the cookie flow only works cross-origin if
the API sets the cookie with `Secure` (it does, in production).

Re-deploy on Vercel after adding the variable (Vite bakes env vars at build time).

---

## 4. CORS & security — what was added/changed

In `lib/ea-bridge/app/main.py` the CORS middleware was hardened:

- `allow_origins=[settings.web_origin]` — exact origin, never `*` (required for
  credentialed cookies).
- `allow_methods` narrowed to `GET, POST, PATCH, DELETE, OPTIONS`.
- `allow_headers` narrowed to `Accept, Content-Type, X-API-Key`.
- `max_age=600` so browsers cache the preflight.
- Security headers added on every response:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`

The legacy `lib/trading-engine/api.py` already had its own CORS via
`CORS_ORIGINS` (env-driven, validated, no wildcards).

`WEB_ORIGIN` must be a bare origin (`https://host[:port]`) — the settings
validator rejects paths, queries, fragments, and non-HTTPS in production.

---

## 5. Database migrations

Blueprint runs `alembic upgrade head` as a deploy job. Manually (from
`lib/ea-bridge` with `DATABASE_URL` set):

```bash
alembic upgrade head
```

## 6. Deploy the MT5 EA (Windows VPS)

1. Rent a Windows VPS (2 vCPU / 4 GB is fine), RDP in.
2. Install MetaTrader 5 using `server/mt5setup.exe`; log into your broker.
3. Copy `AegisQuantEA.mq5` into `MQL5/Experts`, compile in MetaEditor, attach to chart, enable Algo Trading.
4. In the EA inputs set the bridge URL to your Render URL
   (`https://aegis-api-xxxx.onrender.com`) and the `API_TOKEN` from Render.
   Make sure MT5's _Tools → Options → Expert Advisors → Allow WebRequest_ lists
   the Render domain.
5. Pair the device from the Vercel dashboard (**Devices → pairing code**) — the
   EA registers using the pairing code.

## 7. Post-deploy checklist

- [ ] `curl https://<render-api>/healthz` → `{"status":"ok"}`
- [ ] `curl https://<render-api>/readyz` → `{"status":"ready"}`
- [ ] Dashboard signup/login works from the Vercel domain (check the
      `aegis_session` cookie is set, `Secure`, `SameSite=Strict`).
- [ ] Browser console shows no CORS errors (check `WEB_ORIGIN` matches exactly).
- [ ] EA appears under **Devices** after pairing.
- [ ] Signals page populates.
- [ ] Set up uptime monitoring on `/healthz` (Render auto health-checks; add
      BetterStack/UptimeRobot if you want external alerting).

### Railway alternative

If you prefer Railway over Render: `railway up` with a `railway.toml`/Nixpacks
using the same Dockerfile, add Postgres + Redis plugins, and set the same env
vars (`WEB_ORIGIN`, `DATABASE_URL`, `REDIS_URL`, `APP_ENV`, `API_TOKEN`).
Railway gives you a private network URL for Redis instead of the Render
service-name DNS (`aegis-redis:6379` → use the Railway Redis private URL).
