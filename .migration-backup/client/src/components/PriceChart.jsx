import React from "react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import Panel from "./Panel.jsx";

export default function PriceChart({ symbol, series }) {
  const last = series[series.length - 1];

  return (
    <Panel
      title={`${symbol || "—"} · H1 · Line`}
      badge={<span className="font-mono text-[12px] text-ink">{last ? last.price.toFixed(5) : "--"}</span>}
      className="flex-1"
    >
      <div className="mb-2 flex items-center gap-4 text-[11px]">
        <Legend swatch="bg-accent" label="EMA 50" />
        <Legend swatch="bg-warn" dashed label="EMA 200" />
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1e2530" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="time"
              tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              stroke="#5b6272"
              tick={{ fontSize: 10 }}
              minTickGap={40}
            />
            <YAxis
              domain={["auto", "auto"]}
              stroke="#5b6272"
              tick={{ fontSize: 10 }}
              width={58}
              tickFormatter={(v) => v.toFixed(4)}
            />
            <Tooltip
              contentStyle={{ background: "#151a25", border: "1px solid #1e2530", fontSize: 11 }}
              labelFormatter={(t) => new Date(t).toLocaleString()}
            />
            <Line type="monotone" dataKey="price" stroke="#e6e9ef" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="ema50" stroke="#4f8ff7" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="ema200" stroke="#f5a623" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function Legend({ swatch, dashed, label }) {
  return (
    <span className="flex items-center gap-1.5 text-ink-dim">
      <span className={`h-0.5 w-3 ${swatch} ${dashed ? "opacity-70" : ""}`} />
      {label}
    </span>
  );
}