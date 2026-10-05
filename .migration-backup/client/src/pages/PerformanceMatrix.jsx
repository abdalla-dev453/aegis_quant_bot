import { useState, useEffect } from "react";
import { api } from "../lib/api.js";

export default function PerformanceMatrix() {
  const [metrics, setMetrics] = useState({
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    win_rate_pct: "0.0",
    profit_factor: "0.0",
    expectancy: "0.0",
    average_r_multiple: "0.0",
    max_drawdown_pct: "0.0",
    net_pnl: "0.0",
  });
  const [heatmap, setHeatmap] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getJournalMetrics(), api.getJournalHeatmap()])
      .then(([m, h]) => {
        if (m) setMetrics(m);
        if (h) setHeatmap(h || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-8">
      {/* Header */}
      <div className="border-b border-border pb-4">
        <h1 className="text-xl font-bold text-ink">Quantitative Journal & Analytics</h1>
        <p className="mt-1 text-xs text-ink-dim">
          Deep telemetry on AI edge, expectancy distribution, and drawdown recovery.
        </p>
      </div>

      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-[11px] font-mono uppercase text-ink-dim">Win Rate</div>
          <div className="mt-2 font-mono text-2xl font-extrabold text-bull">
            {metrics.win_rate_pct}%
          </div>
          <div className="mt-1 text-[10px] text-ink-faint font-mono">
            {metrics.winning_trades}W / {metrics.losing_trades}L ({metrics.total_trades} Total)
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-[11px] font-mono uppercase text-ink-dim">Profit Factor</div>
          <div className="mt-2 font-mono text-2xl font-extrabold text-accent">
            {metrics.profit_factor}
          </div>
          <div className="mt-1 text-[10px] text-ink-faint font-mono">Gross Wins / Gross Losses</div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-[11px] font-mono uppercase text-ink-dim">Average Expectancy</div>
          <div className="mt-2 font-mono text-2xl font-extrabold text-ink">
            ${metrics.expectancy}
          </div>
          <div className="mt-1 text-[10px] text-ink-faint font-mono">Expected Value / Trade</div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-[11px] font-mono uppercase text-ink-dim">Max Drawdown</div>
          <div className="mt-2 font-mono text-2xl font-extrabold text-bear">
            {metrics.max_drawdown_pct}%
          </div>
          <div className="mt-1 text-[10px] text-ink-faint font-mono">Peak-to-Trough Delta</div>
        </div>
      </div>

      {/* Daily PnL Heatmap */}
      <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-ink uppercase tracking-wider">Daily P/L Distribution</h2>
          <span className="font-mono text-xs text-ink-dim">Calendar Matrix</span>
        </div>

        {loading ? (
          <div className="py-8 text-center text-xs text-ink-dim">Loading telemetry matrix...</div>
        ) : heatmap.length === 0 ? (
          <div className="py-8 text-center text-xs text-ink-dim">No historical trade data recorded yet.</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
            {heatmap.map((entry) => {
              const pnlNum = parseFloat(entry.pnl);
              const isProfit = pnlNum > 0;
              const isLoss = pnlNum < 0;
              return (
                <div
                  key={entry.date}
                  className={`rounded-lg border p-3 font-mono ${
                    isProfit
                      ? "border-bull/30 bg-bull-dim/20 text-bull"
                      : isLoss
                      ? "border-bear/30 bg-bear-dim/20 text-bear"
                      : "border-border bg-canvas text-ink-dim"
                  }`}
                >
                  <div className="text-[10px] text-ink-dim">{entry.date}</div>
                  <div className="mt-1 text-sm font-bold">
                    {isProfit ? `+$${pnlNum.toFixed(2)}` : `$${pnlNum.toFixed(2)}`}
                  </div>
                  <div className="text-[9px] text-ink-faint">{entry.trade_count} trades</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}