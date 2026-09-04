import React from "react";
import Panel from "./Panel.jsx";

function fmtPrice(symbol, value) {
  const digits = symbol === "USDJPY" ? 3 : symbol === "XAUUSD" ? 2 : 5;
  return value.toFixed(digits);
}

export default function PositionsTable({ positions }) {
  return (
    <Panel
      title="Open Positions · Live Execution Ledger"
      badge={
        <span className="rounded bg-bull-dim px-2 py-0.5 text-[10px] font-medium text-bull">
          {positions.length} ACTIVE
        </span>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-[12px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-ink-faint">
              <th className="pb-2 font-medium">Ticket</th>
              <th className="pb-2 font-medium">Asset</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 font-medium">Lot</th>
              <th className="pb-2 font-medium">Entry</th>
              <th className="pb-2 font-medium">Current</th>
              <th className="pb-2 font-medium">SL</th>
              <th className="pb-2 font-medium">TP</th>
              <th className="pb-2 font-medium">Trail</th>
              <th className="pb-2 text-right font-medium">PnL</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {positions.map((p) => {
              const isBuy = p.type === "BUY";
              const pnlPositive = p.pnl >= 0;
              return (
                <tr key={p.ticket} className="border-t border-border">
                  <td className="py-2 text-ink-dim">{p.ticket}</td>
                  <td className="py-2 text-ink">{p.symbol}</td>
                  <td className="py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        isBuy ? "bg-bull-dim text-bull" : "bg-bear-dim text-bear"
                      }`}
                    >
                      {p.type}
                    </span>
                  </td>
                  <td className="py-2 text-ink-dim">{p.lot.toFixed(2)}</td>
                  <td className="py-2 text-ink-dim">{fmtPrice(p.symbol, p.entry)}</td>
                  <td className="py-2 text-ink">{fmtPrice(p.symbol, p.current)}</td>
                  <td className="py-2 text-bear/80">{fmtPrice(p.symbol, p.sl)}</td>
                  <td className="py-2 text-bull/80">{fmtPrice(p.symbol, p.tp)}</td>
                  <td className="py-2 text-ink-faint">{p.trailing ? "on" : "off"}</td>
                  <td className={`py-2 text-right font-semibold ${pnlPositive ? "text-bull" : "text-bear"}`}>
                    {pnlPositive ? "+" : ""}${p.pnl.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}