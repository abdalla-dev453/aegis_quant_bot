import React from "react";
import Panel from "./Panel.jsx";
import { formatPrice } from "../lib/botFeed.js";

export default function TradeAnalysis({ tradeAnalysis }) {
  const { summary, recentTrades } = tradeAnalysis ?? {};
  const total = summary?.totalTrades ?? 0;
  const netPnl = summary?.netPnl ?? 0.0;
  const positive = netPnl >= 0;

  return (
    <Panel
      title="Trade Analysis · Runtime Ledger"
      badge={<span className="font-mono text-[12px] text-ink">{total} trades</span>}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-border bg-surface-alt px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-faint">Total Trades</div>
          <div className="font-mono text-lg font-semibold text-ink">{total}</div>
        </div>
        <div className="rounded-md border border-border bg-surface-alt px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-faint">Net P&L</div>
          <div className={`font-mono text-lg font-semibold ${positive ? "text-bull" : "text-bear"}`}>
            {positive ? "+" : ""}${netPnl.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-1.5">
        {Array.isArray(recentTrades) && recentTrades.length === 0 && (
          <div className="py-4 text-center text-[12px] text-ink-faint">No trades recorded yet.</div>
        )}
        {Array.isArray(recentTrades) && recentTrades.map((trade) => (
          <div
            key={trade.ticket ?? `${trade.symbol}-${trade.direction}`}
            className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-[12px]"
          >
            <div className="flex items-center gap-2">
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                  trade.direction === "BUY" ? "bg-bull-dim text-bull" : "bg-bear-dim text-bear"
                }`}
              >
                {trade.direction}
              </span>
              <span className="text-ink">{trade.symbol}</span>
            </div>
            <div className="font-mono text-ink-dim">
              {formatPrice(trade.symbol, trade.fill_price, 5)} · {trade.volume} lots
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
