# Aegis Quant Python Service

Python trading loop and FastAPI dashboard/control service. OpenAI produces
schema-validated trade proposals; deterministic strategy, portfolio, broker,
and execution checks remain authoritative.

`TRADING_MODE=paper` is the default: it performs data, AI, and broker preflight
checks but suppresses `order_send`. See `../deploy/DEPLOYMENT.md` before any
demo or live rollout.

## Setup

```bash
# Windows only — the MetaTrader5 package wraps the native terminal API
venv\Scripts\python -m pip install -r requirements.txt
```

1. Copy `.env.example` to a local environment file or export its values in
   the shell. Never commit real credentials or API tokens.
2. Open MT5, log into your (ideally **demo**) account once manually so the
   terminal has cached the session.
3. Set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, and `OPENAI_API_KEY` in
   `server/.env` (don't hardcode them in `config.py`). The bot exits before
   connecting to MT5 if its OpenAI credential is missing.
   On Linux, set `MT5LINUX_ENABLED=1` only after the mt5linux bridge has been
   configured; it is deliberately disabled by default.
4. Set a non-empty `API_TOKEN` in `server/.env` and the matching
   `VITE_API_TOKEN` in `client/.env`. The current API requires the token on
   protected routes even in paper mode and on loopback; an empty token causes
   dashboard API requests to return 401.
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

1. **No backtest harness included.** This is live/paper-execution code.
   Validate the strategy logic in `strategy.py` against historical data
   (e.g. via `backtesting.py` or a custom vectorized backtest) before
   running it against a funded account.
2. **Single-process, single-machine.** No distributed locking — don't run
   two instances of `main.py` against the same account/magic number
   simultaneously, or `max_concurrent_positions` accounting will race.
3. **`deviation_points` (slippage tolerance) and `atr_sl_multiplier` /
   `atr_tp_multiplier`** are reasonable starting defaults, not tuned
   values — backtest and adjust per symbol.
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

Use [`../deploy/DEPLOYMENT.md`](../deploy/DEPLOYMENT.md) for the systemd service, Nginx reverse proxy, environment setup, health checks, and demo-account acceptance gate. The default deployment mode is paper trading.
