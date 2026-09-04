# Aegis Quant — Command Dashboard

React + Vite + Tailwind frontend matching the "AEGIS QUANT" Figma design,
built to visualize the MT5 bot's signals, open positions, and equity curve.

## Setup

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## Pages

- **Dashboard** — matches the Figma screenshot: account/risk/performance
  stat cards, EURUSD H1 chart with EMA50/EMA200 overlay, AI Fusion
  confluence gauge, economic calendar/news blackout, live execution log,
  and the open-positions ledger.
- **Performance Matrix** — equity curve (the piece you asked for that
  wasn't in the screenshot), win/loss split, expectancy, and profit
  factor.
- Strategy Builder / Logs / Settings — placeholder pages wired into the
  sidebar nav so the shell is complete; not built out yet.

## Data: currently mock, here's how to go live

Every page reads from a single hook: `src/lib/useBotFeed.js`. It's
currently backed by the generators in `src/lib/botFeed.js`, which update
on a timer to simulate a live feed. **No other component talks to data
directly** — that's deliberate, so swapping mock → real is a one-file change.

Your `main.py` bot is a headless script right now with no API surface, so
you'll need a thin bridge. Recommended: a small FastAPI service run
alongside the bot (or importing its modules directly) exposing:

```
GET  /api/account        -> from data_provider.get_account_equity()
GET  /api/risk           -> derived from account + position data
GET  /api/performance    -> from a trade-history log/DB you maintain
GET  /api/positions      -> from execution.get_open_positions()
GET  /api/equity-curve   -> from a periodically-sampled equity log
GET  /api/confluence     -> from strategy.generate_signal()'s components
GET  /api/calendar       -> from strategy.analyze_market_sentiment()
WS   /ws/logs            -> tail of the bot's log file/handler
```

Then replace the body of `useBotFeed()` with `fetch()` calls on an
interval (or a `WebSocket` for `/ws/logs`) — keep the returned object
shape identical (`account`, `risk`, `performance`, `confluence`,
`calendar`, `positions`, `priceSeries`, `equityCurve`, `logs`) and every
component keeps working unchanged.

One thing to decide on your end: `main.py` currently runs its own asyncio
loop with no HTTP server in it. The cleanest approach is usually a
**separate FastAPI process** that reads the bot's positions/equity from
MT5 directly (same account, read-only calls) rather than modifying
`main.py` itself — keeps the trading loop's timing untouched by dashboard
traffic.

## Design tokens (matched from the Figma screenshots)

- Background: `#0a0d14` (page) / `#10141d` (cards)
- Text: `#e6e9ef` (primary) / `#8991a3` (labels) / `#5b6272` (timestamps)
- Signals: bull `#22d67e`, bear `#ff4d5e`, accent/info `#4f8ff7`, warn `#f5a623`
- Type: Inter (UI text), JetBrains Mono (all numeric/ticker data)

All defined in `tailwind.config.js` under the `colors` and `fontFamily` keys.