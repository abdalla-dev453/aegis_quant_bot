/**
 * lib/botFeed.js
 * -----------------------------------------------------------------------
 * API client + single source of truth for "what shape does bot data come
 * in as". Mirrors server/models.py exactly — if a field changes there,
 * change it here (and only here).
 *
 * All endpoints are served by the Python bot's FastAPI bridge:
 *   GET /api/account      -> AccountState
 *   GET /api/risk         -> RiskState
 *   GET /api/performance  -> PerformanceState
 *   GET /api/confluence   -> ConfluenceState
 *   GET /api/calendar     -> CalendarState
 *   GET /api/positions    -> Position[]
 *   GET /api/equity-curve -> EquityPoint[]
 *   GET /api/price-series -> PricePoint[]
 *   GET /api/logs         -> LogEntry[]
 */

const API_BASE = import.meta.env?.VITE_API_BASE ?? "http://localhost:8000";

// Symbols come from the server (TRADING_SYMBOLS in config.py) inside the
// /api/price-series and /api/positions payloads — no client-side list.

/** Small fetch wrapper: JSON, timeout, and normalized error handling. */
async function apiGet(path, { timeoutMs = 5000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`API ${path} failed: HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function apiPost(path, body, { timeoutMs = 10000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok)
      throw new Error(
        payload.detail ?? `API ${path} failed: HTTP ${res.status}`,
      );
    return payload;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Coercion helpers — a partial/NaN payload must never crash the UI.
// ---------------------------------------------------------------------------

const num = (v, fallback = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

const clamp1 = (v) => Math.max(-1, Math.min(1, num(v)));

// ---------------------------------------------------------------------------
// Typed accessors — each returns the exact shape in server/models.py.
// ---------------------------------------------------------------------------

export async function fetchAccount() {
  const d = await apiGet("/api/account");
  return {
    netEquity: num(d.netEquity),
    balance: num(d.balance),
    todaysPnl: num(d.todaysPnl),
    freeMargin: num(d.freeMargin),
    marginLevel: num(d.marginLevel),
  };
}

export async function fetchRisk() {
  const d = await apiGet("/api/risk");
  return {
    drawdownPct: num(d.drawdownPct),
    maxDrawdownCeilingPct: num(d.maxDrawdownCeilingPct, 5.0),
    marginUtilizedPct: num(d.marginUtilizedPct),
    openPositions: Math.max(0, Math.trunc(num(d.openPositions))),
    dailyVaR: num(d.dailyVaR),
    riskPerTradePct: d.riskPerTradePct != null ? num(d.riskPerTradePct) : null,
  };
}

export async function fetchPerformance() {
  const d = await apiGet("/api/performance");
  return {
    winRatePct: num(d.winRatePct),
    profitFactor: num(d.profitFactor),
    totalTrades: Math.max(0, Math.trunc(num(d.totalTrades))),
    avgWin: num(d.avgWin),
    avgLoss: num(d.avgLoss),
  };
}

export async function fetchConfluence() {
  const d = await apiGet("/api/confluence");
  return {
    composite: clamp1(d.composite),
    label: typeof d.label === "string" ? d.label : "NEUTRAL",
    technical: clamp1(d.technical),
    sentiment: clamp1(d.sentiment),
    momentum: clamp1(d.momentum),
  };
}

export async function fetchCalendar() {
  const d = await apiGet("/api/calendar");
  return {
    autoHaltActive: Boolean(d.autoHaltActive),
    autoHaltEtaSeconds: Math.max(0, Math.trunc(num(d.autoHaltEtaSeconds))),
    nextEvent: d.nextEvent
      ? {
          name: String(d.nextEvent.name ?? "Unknown"),
          currency: String(d.nextEvent.currency ?? ""),
          impact: String(d.nextEvent.impact ?? "LOW"),
          timeUtc: String(d.nextEvent.timeUtc ?? "--:--"),
          minutesAway: num(d.nextEvent.minutesAway),
        }
      : null,
  };
}

export async function fetchPositions() {
  const rows = await apiGet("/api/positions");
  if (!Array.isArray(rows)) return [];
  return rows.map((d) => ({
    ticket: String(d.ticket ?? ""),
    symbol: String(d.symbol ?? ""),
    type: d.type === "SELL" ? "SELL" : "BUY",
    lot: num(d.lot),
    entry: num(d.entry),
    sl: num(d.sl),
    tp: num(d.tp),
    trailing: Boolean(d.trailing),
    current: num(d.current),
    pnl: num(d.pnl),
    digits: Number.isFinite(Number(d.digits)) ? Number(d.digits) : undefined,
  }));
}

export async function fetchEquityCurve() {
  const rows = await apiGet("/api/equity-curve");
  if (!Array.isArray(rows)) return [];
  return rows.map((d) => ({ date: String(d.date), equity: num(d.equity) }));
}

export async function fetchPriceSeries() {
  const payload = await apiGet("/api/price-series");
  // Contract: { symbol: string, points: PricePoint[] }
  const rows = Array.isArray(payload) ? payload : payload?.points;
  const points = Array.isArray(rows)
    ? rows.map((d) => ({
        time: String(d.time),
        price: num(d.price),
        ema50: num(d.ema50),
        ema200: num(d.ema200),
      }))
    : [];
  return {
    symbol: Array.isArray(payload) ? "" : String(payload?.symbol ?? ""),
    points,
  };
}

export async function fetchLogs() {
  const rows = await apiGet("/api/logs");
  if (!Array.isArray(rows)) return [];
  return rows.map((d) => ({
    id: String(d.id ?? `${Date.now()}-${Math.random()}`),
    time: String(d.time ?? ""),
    level: ["INFO", "WARN", "ERROR"].includes(d.level) ? d.level : "INFO",
    message: String(d.message ?? ""),
  }));
}

export async function fetchSettings() {
  const d = await apiGet("/api/settings");
  return {
    credentialsConfigured: Boolean(d.credentialsConfigured),
    symbols: Array.isArray(d.symbols) ? d.symbols.map(String) : [],
    timeframeTrigger: String(d.timeframeTrigger ?? "H1"),
    timeframeBias: String(d.timeframeBias ?? "H4"),
    riskPerTradePct: num(d.riskPerTradePct),
    atrStopMultiplier: num(d.atrStopMultiplier),
    atrTakeProfitMultiplier: num(d.atrTakeProfitMultiplier),
    maxConcurrentPositions: Math.max(
      0,
      Math.trunc(num(d.maxConcurrentPositions)),
    ),
    magicNumber: String(d.magicNumber ?? ""),
  };
}

export function saveCredentials(credentials) {
  return apiPost("/api/settings/credentials", credentials);
}

/**
 * Format a price with the correct decimal precision for a symbol.
 * Prefers server-provided digits; falls back to a broker-neutral heuristic.
 */
export function formatPrice(symbol, value, digits) {
  const d =
    digits ?? (symbol === "XAUUSD" ? 2 : symbol.endsWith("JPY") ? 3 : 5);
  return num(value).toFixed(d);
}
