import React from "react";
import Panel from "./Panel.jsx";

export default function RecentOrders({ orders }) {
  return (
    <Panel
      title="Recent Orders · AI Decisions"
      badge={<span className="font-mono text-[12px] text-ink">{(orders ?? []).length} records</span>}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[12px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-ink-faint">
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2 font-medium">Symbol</th>
              <th className="pb-2 font-medium">Action</th>
              <th className="pb-2 font-medium">Volume</th>
              <th className="pb-2 font-medium">Confidence</th>
              <th className="pb-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {(orders ?? []).map((order, idx) => {
              const blocked = order.status !== "filled";
              return (
                <tr key={order.ticket ?? `order-${idx}`} className="border-t border-border">
                  <td className="py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        blocked ? "bg-warn-dim text-warn" : "bg-bull-dim text-bull"
                      }`}
                    >
                      {order.status}
                    </span>
                  </td>
                  <td className="py-2 text-ink">{order.symbol}</td>
                  <td className="py-2">{order.action}</td>
                  <td className="py-2 text-ink-dim">{order.volume}</td>
                  <td className="py-2 text-ink-dim">{order.confidence_score?.toFixed(2) ?? "--"}</td>
                  <td className="py-2 truncate text-ink-dim" title={order.reason}>
                    {order.reason}
                  </td>
                </tr>
              );
            })}
            {(orders ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-center text-[12px] text-ink-faint">
                  No proposals or orders recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
