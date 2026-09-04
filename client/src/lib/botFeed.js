/**
 * lib/botFeed.js
 * -----------------------------------------------------------------------
 * Single source of truth for "what shape does bot data come in as".
 *
 * Right now `useBotFeed()` (in hooks below) is backed by the mock
 * generator in this file, updating on an interval to simulate a live
 * connection. To go live, replace the body of `useBotFeed` with a
 * WebSocket subscription or polling fetch against a real backend —
 * every component downstream only depends on the shapes documented here,
 * so nothing else needs to change.
 *
 * Suggested real backend: a small FastAPI service alongside the Python
 * bot that exposes:
 *   GET  /api/account        -> AccountState
 *   GET  /api/risk           -> RiskState
 *   GET  /api/performance    -> PerformanceState
 *   GET  /api/positions      -> Position[]
 *   GET  /api/equity-curve   -> EquityPoint[]
 *   GET  /api/confluence     -> ConfluenceState
 *   GET  /api/calendar       -> CalendarEvent[]
 *   WS   /ws/logs            -> stream of LogEntry
 * reading straight from data_provider.get_account_equity(),
 * execution.get_open_positions(), and a rotating log handler.
 */

const SYMBOLS = ["EURUSD", "XAUUSD", "GBPUSD", "USDJPY"];

let seed = 42;
function rand() {
  // deterministic-ish PRNG so mock data doesn't feel too jittery frame to frame
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}

function randRange(min, max) {
  return min + rand() * (max - min);
}

// ---------------------------------------------------------------------------
// Price series for the main chart (EURUSD H1 with EMA50 / EMA200 overlay)
// ---------------------------------------------------------------------------
export function generatePriceSeries(points = 60, basePrice = 1.0855) {
  const series = [];
  let price = basePrice;
  const now = Date.now();

  for (let i = 0; i < points; i++) {
    price += randRange(-0.0006, 0.00055);
    series.push({
      time: new Date(now - (points - i) * 60 * 60 * 1000).toISOString(),
      price: Number(price.toFixed(5)),
    });
  }

  // Simple EMA calculation so the overlay is mathematically consistent
  // with the underlying series, not just decorative lines.
  const ema = (period) => {
    const k = 2 / (period + 1);
    let prev = series[0].price;
    return series.map((p) => {
      prev = p.price * k + prev * (1 - k);
      return Number(prev.toFixed(5));
    });
  };

  const ema50 = ema(Math.min(50, Math.floor(points / 2)));
  const ema200 = ema(Math.min(200, points));

  return series.map((p, i) => ({ ...p, ema50: ema50[i], ema200: ema200[i] }));
}

// ---------------------------------------------------------------------------
// Equity curve for the Performance Matrix page
// ---------------------------------------------------------------------------
export function generateEquityCurve(points = 90, startEquity = 42000) {
  const series = [];
  let equity = startEquity;
  const now = Date.now();

  for (let i = 0; i < points; i++) {
    const drift = randRange(-140, 210);
    equity = Math.max(equity + drift, startEquity * 0.85);
    series.push({
      date: new Date(now - (points - i) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      equity: Number(equity.toFixed(2)),
    });
  }
  return series;
}

// ---------------------------------------------------------------------------
// Static-ish snapshots (would be GET requests against a real backend)
// ---------------------------------------------------------------------------
export function generateAccountState() {
  return {
    netEquity: 48518.67,
    balance: 48234.17,
    todaysPnl: 284.5,
    freeMargin: 29704.85,
    marginLevel: 612.3,
  };
}

export function generateRiskState() {
  return {
    drawdownPct: 1.82,
    maxDrawdownCeilingPct: 5.0,
    marginUtilizedPct: 38.2,
    openPositions: 5,
    dailyVaR: 902.08,
  };
}

export function generatePerformanceState() {
  return {
    winRatePct: 68.4,
    profitFactor: 2.34,
    totalTrades: 247,
    avgWin: 183.4,
    avgLoss: -78.2,
  };
}

export function generateConfluenceState() {
  return {
    composite: 0.78,
    label: "STRONG BULL",
    technical: 0.74,
    sentiment: 0.78,
    momentum: 0.82,
  };
}

export function generateCalendarState() {
  return {
    autoHaltActive: true,
    autoHaltEtaSeconds: 605,
    nextEvent: {
      name: "US CPI Release",
      currency: "USD",
      impact: "HIGH",
      timeUtc: "14:30",
      minutesAway: 45,
    },
  };
}

export function generatePositions() {
  const rows = [
    { ticket: "TK-20847", symbol: "EURUSD", type: "BUY", lot: 0.15, entry: 1.08312, sl: 1.08112, tp: 1.08712, trailing: true },
    { ticket: "TK-20851", symbol: "XAUUSD", type: "SELL", lot: 0.05, entry: 2318.4, sl: 2328.0, tp: 2300.0, trailing: false },
    { ticket: "TK-20863", symbol: "GBPUSD", type: "BUY", lot: 0.1, entry: 1.26741, sl: 1.26441, tp: 1.27241, trailing: true },
    { ticket: "TK-20872", symbol: "USDJPY", type: "SELL", lot: 0.2, entry: 151.823, sl: 152.325, tp: 151.023, trailing: true },
    { ticket: "TK-20891", symbol: "EURUSD", type: "BUY", lot: 0.1, entry: 1.08421, sl: 1.08221, tp: 1.08821, trailing: true },
  ];

  return rows.map((r) => {
    const drift = randRange(-0.0004, 0.0004) * (r.symbol === "USDJPY" ? 200 : r.symbol === "XAUUSD" ? 8000 : 1);
    const current = Number((r.entry + drift).toFixed(r.symbol === "USDJPY" || r.symbol === "XAUUSD" ? 3 : 5));
    const dir = r.type === "BUY" ? 1 : -1;
    const pnl = Number((dir * (current - r.entry) * r.lot * (r.symbol === "USDJPY" ? 900 : r.symbol === "XAUUSD" ? 100 : 90000)).toFixed(2));
    return { ...r, current, pnl };
  });
}

const LOG_TEMPLATES = [
  { level: "INFO", text: (s) => `${s} price tick: updated` },
  { level: "INFO", text: () => "EMA recalculation complete. Trend: BULLISH" },
  { level: "INFO", text: () => "MT5 heartbeat OK. Ping: 12ms." },
  { level: "INFO", text: () => "Risk engine cycle complete. All limits within bounds." },
  { level: "WARN", text: () => "News feed polled. No sentiment shift detected." },
];

export function generateLogEntry() {
  const t = LOG_TEMPLATES[Math.floor(rand() * LOG_TEMPLATES.length)];
  const symbol = SYMBOLS[Math.floor(rand() * SYMBOLS.length)];
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return {
    id: `${now.getTime()}-${Math.floor(rand() * 1e6)}`,
    time: `${hh}:${mm}:${ss}`,
    level: t.level,
    message: t.text(symbol),
  };
}