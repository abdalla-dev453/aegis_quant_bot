# Aegis Quant Python Service

Selected execution candidate for qualification: the Python trading loop and
FastAPI dashboard/control service running beside the MT5 terminal on Windows.
OpenAI produces schema-validated proposals; deterministic strategy, portfolio,
broker, and execution checks remain authoritative. Do not attach the standalone
MQL5 EAs or enable the EA bridge as another executor on the same account.

`TRADING_MODE=paper` is the default: it performs data, AI, and broker preflight
checks but suppresses `order_send`. See `../../docs/PRE_DEPLOYMENT_RELEASE_PLAN.md`
before a demo or live rollout.

## Setup

```bash
# Run from lib/trading-engine in PowerShell; MetaTrader5 requires Windows.
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

1. Copy `.env.example` to a local environment file or export its values in
   the shell. Never commit real credentials or API tokens.
2. Open MT5, log into your (ideally **demo**) account once manually so the
   terminal has cached the session.
3. Set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_EXPECTED_LOGIN`,
   `MT5_EXPECTED_SERVER`, and `OPENAI_API_KEY` in `lib/trading-engine/.env`
   (don't hardcode them in `config.py`). The bot exits before
   connecting to MT5 if its OpenAI credential is missing.
   On Linux, set `MT5LINUX_ENABLED=1` only after the mt5linux bridge has been
   configured; it is deliberately disabled by default.
4. Set a long random `API_TOKEN` in the service `.env`. The local React client
   currently sends a build-time `VITE_API_TOKEN`; that exposes the shared token
   to anyone who can load those browser assets. Do not deploy that token in a
   public dashboard build. Until session-based operator authentication replaces
   the shared browser token, keep this Python control dashboard on an isolated
   local/private host. The hosted `artifacts/onyx-fx` dashboard is a separate
   application and uses the EA bridge, whose signal dispatch remains disabled.
5. Adjust `TRADING_SYMBOLS` and `RISK` in `config.py` to match your broker's
   symbol names (e.g. some brokers suffix `.a`, `EURUSD.pro`, etc.) and your
   real risk tolerance.
6. Run:

   ```bash
   python main.py
   ```

The frontend defaults to `http://localhost:8000` and starts in `System` theme
mode. Use the theme menu in the top bar to choose `Light`, `Dark`, or `System`;
the selection is saved in the browser. `python main.py` starts both the API
and the Python trading loop.

## File map

| File               | Responsibility                                                               |
| ------------------ | ---------------------------------------------------------------------------- |
| `config.py`        | All settings — credentials, symbols, indicator/risk params. No side effects. |
| `data_provider.py` | MT5 connection lifecycle, reconnection, candle/account data fetching.        |
| `strategy.py`      | Closed-candle indicator computation used as AI market context.                |
| `ai_engine.py`     | GPT-4o JSON-mode call, Pydantic proposal validation, fail-closed HOLD.       |
| `news_provider.py` | MT5 calendar/news adapter, NewsAPI/Yahoo fallback, cleaning and caching.     |
| `execution.py`     | Risk validation, MT5 `order_send`, and trailing stop management.              |
| `main.py`          | Async loop — polls closed candles and dispatches validated AI proposals.      |

## Known limitations to address before going live

1. **Research harness is only an initial screen.** Run
   `scripts/backtest_python_strategy.py` with broker-specific candle and cost
   data, then validate using MT5 Strategy Tester. The harness omits news,
   swaps, trailing stops, partial fills, and broker-specific execution.
2. **Single-process, single-machine.** No distributed locking — don't run
   two instances of `main.py` against the same account/magic number
   simultaneously, or `max_concurrent_positions` accounting will race.
3. **No performance or broker evidence is included.** Risk and indicator
   defaults are unapproved starting values. Backtest and qualify each intended
   symbol on the selected broker before any funded account.
4. Paper mode suppresses new entries and automatic trailing-stop modifications.
   HALTED also disables automatic position management. The explicit,
   authenticated close-positions operator action remains available in either
   execution mode and submits broker market orders for bot-owned positions.
5. The dashboard reports execution mode separately from RUNNING/PAUSED/HALTED
   operator control state. Re-arming HALTED through the dashboard requires
   confirmation; direct authenticated API control changes remain possible.

## Architecture notes

- **AI proposal boundary**: GPT-4o receives only closed-candle H1/H4 indicator
  values and returns JSON mode output at temperature 0.0. Pydantic rejects any
  non-conforming response, logs the raw reply only to `error.log`, and emits a
  fail-closed HOLD instead.
- **Live macro context**: the bot first attempts a calendar/news method exposed
  by the connected MT5 bridge (including mt5linux). If unavailable, it uses an
  optional `NEWS_API_KEY` feed then Yahoo Finance RSS. All sources are normalized
  and only high-impact items from the prior 24 hours reach the LLM.
- **Never trades on a forming candle**: `data_provider.get_rates()` uses
  `copy_rates_from_pos(..., start_pos=1, ...)`, always skipping the
  currently-open candle, and `main.py`'s `LastCandleTracker` re-evaluates a
  symbol only once its H1 candle has actually closed.
- **Position sizing is broker-aware**: uses `symbol_info().trade_tick_value`
  / `trade_tick_size` rather than a hardcoded pip value, so 1.5% risk is
  accurate across FX pairs, JPY pairs, and metals alike.

- **Dashboard data is API-backed**: `client/src/lib/botFeed.js` polls the
   FastAPI service; it is not backed by mock generators. Operator actions are
   authenticated. The explicit close-positions action is limited to the
   configured bot magic number and submits market close requests.

## Deployment

Use [`../../docs/PLATFORM_DEPLOYMENT.md`](../../docs/PLATFORM_DEPLOYMENT.md) for deployment guidance and [`../../docs/PRE_DEPLOYMENT_RELEASE_PLAN.md`](../../docs/PRE_DEPLOYMENT_RELEASE_PLAN.md) for the selected candidate and release gates. The default mode is paper trading. Live execution remains NO-GO until all gates are evidenced and approved. Keep MT5 and Python on one dedicated Windows host; do not use Vercel, Netlify, Railway, or Render for the order process.

## Order intent and recovery

Live orders require a stable signal ID derived from symbol, closed-candle time,
and direction. The engine persists an intent in `EXECUTION_INTENT_FILE` before
calling `order_send`; a repeat ID is never sent again. A crash or ambiguous
broker response leaves an unresolved `SUBMITTING`/`UNKNOWN`/`PARTIAL` intent,
which blocks API re-arm. Reconcile broker order/deal/position history, then
record the evidence through `POST /api/execution/intents/{signal_id}/reconcile`
before setting control to `RUNNING`. Protect and back up this file with other
risk state. This is single-process local durability, not a distributed lock or
a substitute for broker reconciliation.

## Historical research

Export separate H1 and H4 MT5 candles to CSV with `time,open,high,low,close`
columns. Run `python scripts/backtest_python_strategy.py --help` from the
repository root for required instrument cost inputs. The runner splits the
history chronologically into development and out-of-sample windows, uses only
closed candles, applies spread/slippage/commission, and assumes stop-first when
both stop and target fall inside one bar. The resulting JSON is research
evidence only; it is not a full-bot or MT5 Strategy Tester report. It omits LLM
proposal sizing, portfolio checks, swaps, news, trailing management, and
broker-specific order behavior.
