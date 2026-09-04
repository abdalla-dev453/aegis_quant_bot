import React from "react";
import TopBar from "../components/TopBar.jsx";
import EquityCurveChart from "../components/EquityCurveChart.jsx";
import Panel from "../components/Panel.jsx";
import { PerformanceCard } from "../components/StatCards.jsx";
import { useBotFeed } from "../lib/useBotFeed.js";

export default function PerformanceMatrix() {
  const { performance, equityCurve, positions } = useBotFeed();

  const winners = positions.filter((p) => p.pnl >= 0).length;
  const losers = positions.length - winners;

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <TopBar title="Performance Matrix" subtitle="Historical equity, win/loss distribution, and trade quality" />

      <div className="flex-1 space-y-4 overflow-y-auto px-8 py-5">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <EquityCurveChart series={equityCurve} />
          </div>
          <PerformanceCard performance={performance} />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Panel title="Open Trade Split">
            <div className="flex items-center justify-around py-2">
              <SplitStat label="Winning" value={winners} tone="bull" />
              <SplitStat label="Losing" value={losers} tone="bear" />
            </div>
          </Panel>
          <Panel title="Expectancy">
            <div className="py-2 text-center">
              <div className="font-mono text-2xl font-semibold text-ink">
                ${(
                  (performance.winRatePct / 100) * performance.avgWin +
                  (1 - performance.winRatePct / 100) * performance.avgLoss
                ).toFixed(2)}
              </div>
              <div className="mt-1 text-[10px] uppercase tracking-wider text-ink-faint">
                Expected value per trade
              </div>
            </div>
          </Panel>
          <Panel title="Risk-Adjusted">
            <div className="py-2 text-center">
              <div className="font-mono text-2xl font-semibold text-accent">{performance.profitFactor.toFixed(2)}</div>
              <div className="mt-1 text-[10px] uppercase tracking-wider text-ink-faint">Profit factor</div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function SplitStat({ label, value, tone }) {
  const toneClass = tone === "bull" ? "text-bull" : "text-bear";
  return (
    <div className="text-center">
      <div className={`font-mono text-3xl font-semibold ${toneClass}`}>{value}</div>
      <div className="mt-1 text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
    </div>
  );
}