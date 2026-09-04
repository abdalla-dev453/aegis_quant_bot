import React from "react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import Panel from "./Panel.jsx";

export default function EquityCurveChart({ series }) {
  const first = series[0]?.equity ?? 0;
  const last = series[series.length - 1]?.equity ?? 0;
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const positive = changePct >= 0;

  return (
    <Panel
      title="Equity Curve · 90D"
      badge={
        <span className={`font-mono text-[12px] ${positive ? "text-bull" : "text-bear"}`}>
          {positive ? "+" : ""}
          {changePct.toFixed(2)}%
        </span>
      }
      className="flex-1"
    >
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d67e" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#22d67e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1e2530" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#5b6272"
              tick={{ fontSize: 10 }}
              minTickGap={50}
              tickFormatter={(d) => new Date(d).toLocaleDateString([], { month: "short", day: "numeric" })}
            />
            <YAxis
              stroke="#5b6272"
              tick={{ fontSize: 10 }}
              width={64}
              domain={["auto", "auto"]}
              tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
            />
            <Tooltip
              contentStyle={{ background: "#151a25", border: "1px solid #1e2530", fontSize: 11 }}
              formatter={(v) => [`$${v.toLocaleString()}`, "Equity"]}
              labelFormatter={(d) => new Date(d).toLocaleDateString()}
            />
            <Area type="monotone" dataKey="equity" stroke="#22d67e" strokeWidth={1.75} fill="url(#equityFill)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}