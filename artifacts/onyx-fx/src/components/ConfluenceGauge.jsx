import React from "react";
import Panel from "./Panel.jsx";

export default function ConfluenceGauge({ confluence }) {
  // Map score range [-1, 1] to a semicircle sweep from 180deg (left) to 0deg (right)
  const clamped = Math.max(-1, Math.min(1, confluence.composite));
  const angle = 180 - ((clamped + 1) / 2) * 180;
  const needleColor = clamped >= 0.3 ? "#22d67e" : clamped <= -0.3 ? "#ff4d5e" : "#f5a623";

  const rad = (angle * Math.PI) / 180;
  const cx = 100;
  const cy = 92;
  const r = 70;
  const nx = cx + r * Math.cos(rad);
  const ny = cy - r * Math.sin(rad);

  return (
    <Panel title="AI Fusion Confluence Score">
      <div className="flex flex-col items-center">
        <svg width="200" height="110" viewBox="0 0 200 110">
          <path d="M 30 92 A 70 70 0 0 1 170 92" fill="none" stroke="#1e2530" strokeWidth="10" strokeLinecap="round" />
          <path
            d="M 30 92 A 70 70 0 0 1 170 92"
            fill="none"
            stroke="url(#gaugeGradient)"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${((clamped + 1) / 2) * 220} 220`}
          />
          <defs>
            <linearGradient id="gaugeGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#ff4d5e" />
              <stop offset="50%" stopColor="#f5a623" />
              <stop offset="100%" stopColor="#22d67e" />
            </linearGradient>
          </defs>
          <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={needleColor} strokeWidth="2.5" strokeLinecap="round" />
          <circle cx={cx} cy={cy} r="4" fill={needleColor} />
        </svg>
        <div className="-mt-2 font-mono text-2xl font-semibold" style={{ color: needleColor }}>
          {clamped >= 0 ? "+" : ""}
          {clamped.toFixed(2)}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-ink-faint">{confluence.label}</div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <SubScore label="Technical" value={confluence.technical} />
        <SubScore label="Sentiment" value={confluence.sentiment} />
        <SubScore label="Momentum" value={confluence.momentum} />
      </div>
    </Panel>
  );
}

function SubScore({ label, value }) {
  const tone = value >= 0.3 ? "text-bull" : value <= -0.3 ? "text-bear" : "text-warn";
  return (
    <div className="rounded-md border border-border bg-surface-alt px-2 py-1.5 text-center">
      <div className={`font-mono text-[12px] ${tone}`}>
        {value >= 0 ? "+" : ""}
        {value.toFixed(2)}
      </div>
      <div className="mt-0.5 text-[9px] uppercase tracking-wider text-ink-faint">{label}</div>
    </div>
  );
}