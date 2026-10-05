import React from "react";
import Panel from "./Panel.jsx";

const currency = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value ?? 0);

function signalTime(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "--:--"
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function Metric({ label, value, tone }) {
  return (
    <div className="min-w-0 border-l border-border pl-3 first:border-l-0 first:pl-0">
      <dt className="text-[10px] uppercase text-ink-faint">{label}</dt>
      <dd className={`mt-1 truncate font-mono text-sm ${tone ?? "text-ink"}`}>{value}</dd>
    </div>
  );
}

export default function BotStatusPanel({
  account,
  risk,
  control,
  proposals,
  orders,
  logs,
  connected,
  aiConfigured,
  tradingMode,
}) {
  const lastSignal = proposals.at(-1);
  const lastOrder = orders.at(-1);
  const lastEvent = logs.at(-1);
  const status = control?.status ?? "RUNNING";
  const signal = lastSignal
    ? `${lastSignal.action} ${lastSignal.symbol} ${signalTime(lastSignal.candle_time)}`
    : "NONE";
  const order = lastOrder
    ? `${lastOrder.status.toUpperCase()} ${lastOrder.direction} ${lastOrder.symbol}`
    : "NONE";

  return (
    <Panel
      title="AI Trading Bot"
      badge={(
        <span className={`flex items-center gap-1.5 font-mono text-[11px] ${status === "RUNNING" ? "text-bull" : "text-warn"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${status === "RUNNING" ? "bg-bull" : "bg-warn"}`} />
          {tradingMode} / {status}
        </span>
      )}
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4 xl:grid-cols-8">
        <Metric label="Equity" value={currency(account.netEquity)} />
        <Metric label="Daily P/L" value={currency(account.todaysPnl)} tone={account.todaysPnl < 0 ? "text-bear" : "text-bull"} />
        <Metric label="Drawdown" value={`${risk.drawdownPct.toFixed(2)}%`} />
        <Metric label="Open positions" value={risk.openPositions} />
        <Metric label="Risk / trade" value={risk.riskPerTradePct == null ? "--" : `${risk.riskPerTradePct.toFixed(2)}%`} />
        <Metric label="AI API" value={aiConfigured ? "CONFIGURED" : "NOT CONFIGURED"} tone={aiConfigured ? "text-bull" : "text-warn"} />
        <Metric label="Feed" value={connected ? "CONNECTED" : "OFFLINE"} tone={connected ? "text-bull" : "text-bear"} />
        <Metric label="Last signal" value={signal} />
      </dl>
      <div className="mt-4 grid gap-3 border-t border-border pt-3 text-[11px] sm:grid-cols-2">
        <p className="min-w-0 truncate text-ink-dim"><span className="text-ink-faint">Last order</span><span className="mx-2 text-border">/</span>{order}</p>
        <p className="min-w-0 wrap-break-word text-ink-dim"><span className="text-ink-faint">Last event</span><span className="mx-2 text-border">/</span>{lastEvent?.message ?? "--"}</p>
      </div>
    </Panel>
  );
}