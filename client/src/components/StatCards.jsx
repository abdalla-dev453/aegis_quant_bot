import React from "react";
import Panel from "./Panel.jsx";

function money(n, opts = {}) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", ...opts });
}

export function AccountCard({ account }) {
  const pnlPositive = account.todaysPnl >= 0;
  return (
    <Panel title="Account · Equity & Balance">
      <div className="font-mono text-2xl font-semibold text-ink">{money(account.netEquity)}</div>
      <div className="mt-4 grid grid-cols-2 gap-y-3 text-[12px]">
        <Metric label="Balance" value={money(account.balance)} />
        <Metric
          label="Today's P/L"
          value={`${pnlPositive ? "+" : ""}${money(account.todaysPnl)}`}
          tone={pnlPositive ? "bull" : "bear"}
        />
        <Metric label="Free Margin" value={money(account.freeMargin)} />
        <Metric label="Margin Level" value={`${account.marginLevel.toFixed(1)}%`} />
      </div>
    </Panel>
  );
}

export function RiskCard({ risk }) {
  const pct = Math.min(100, (risk.drawdownPct / risk.maxDrawdownCeilingPct) * 100);
  return (
    <Panel title="Risk Exposure · Live">
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] text-ink-dim">Drawdown</span>
        <span className="font-mono text-[12px] text-ink">
          {risk.drawdownPct.toFixed(2)}% / {risk.maxDrawdownCeilingPct.toFixed(0)}%
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-alt">
        <div
          className={`h-full rounded-full ${pct > 80 ? "bg-bear" : pct > 50 ? "bg-warn" : "bg-bull"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-y-3 text-[12px]">
        <Metric label="Margin Utilized" value={`${risk.marginUtilizedPct.toFixed(1)}%`} />
        <Metric label="Open Positions" value={risk.openPositions} />
        <Metric label="Max DD Ceiling" value={`${risk.maxDrawdownCeilingPct.toFixed(2)}%`} />
        <Metric label="Daily VaR" value={money(risk.dailyVaR)} />
      </div>
    </Panel>
  );
}

export function PerformanceCard({ performance }) {
  return (
    <Panel title="Truth Metric · Performance">
      <div className="grid grid-cols-3 gap-2">
        <TripleStat label="Win Rate" value={`${performance.winRatePct.toFixed(1)}%`} tone="bull" />
        <TripleStat label="Profit Factor" value={performance.profitFactor.toFixed(2)} tone="accent" />
        <TripleStat label="Total Trades" value={performance.totalTrades} tone="ink" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-y-3 text-[12px]">
        <Metric label="Avg Win" value={`+${money(performance.avgWin)}`} tone="bull" />
        <Metric label="Avg Loss" value={money(performance.avgLoss)} tone="bear" />
      </div>
    </Panel>
  );
}

function Metric({ label, value, tone }) {
  const toneClass = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-ink";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
      <div className={`mt-0.5 font-mono text-[13px] ${toneClass}`}>{value}</div>
    </div>
  );
}

function TripleStat({ label, value, tone }) {
  const toneClass = { bull: "text-bull", accent: "text-accent", ink: "text-ink" }[tone];
  return (
    <div className="rounded-md border border-border bg-surface-alt px-2 py-2 text-center">
      <div className={`font-mono text-lg font-semibold ${toneClass}`}>{value}</div>
      <div className="mt-0.5 text-[9px] uppercase tracking-wider text-ink-faint">{label}</div>
    </div>
  );
}