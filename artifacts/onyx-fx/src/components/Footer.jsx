import React from "react";

export default function Footer({ totalFloat, riskPerTradePct }) {
  const positive = totalFloat >= 0;
  return (
    <div className="flex items-center justify-between border-t border-border px-8 py-3 text-[11px]">
      <span className="text-ink-faint">
        Dynamic Risk: {riskPerTradePct != null ? `${riskPerTradePct}%` : "—"} per trade · Hard SL enforced on all positions
      </span>
      <span className={`font-mono ${positive ? "text-bull" : "text-bear"}`}>
        Total Float: {positive ? "+" : ""}${totalFloat.toFixed(2)}
      </span>
    </div>
  );
}