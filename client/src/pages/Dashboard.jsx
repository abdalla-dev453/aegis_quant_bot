import React from "react";
import TopBar from "../components/TopBar.jsx";
import { AccountCard, RiskCard, PerformanceCard } from "../components/StatCards.jsx";
import PriceChart from "../components/PriceChart.jsx";
import ConfluenceGauge from "../components/ConfluenceGauge.jsx";
import EconomicCalendar from "../components/EconomicCalendar.jsx";
import ExecutionLog from "../components/ExecutionLog.jsx";
import PositionsTable from "../components/PositionsTable.jsx";
import Footer from "../components/Footer.jsx";
import { useBotFeed } from "../lib/useBotFeed.js";

export default function Dashboard() {
  const { account, risk, performance, confluence, calendar, positions, priceSeries, logs, connected } = useBotFeed();

  const totalFloat = positions.reduce((sum, p) => sum + p.pnl, 0);
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <TopBar
        title="Command Dashboard"
        subtitle={`${today} · ${connected ? "Feed Connected" : "Feed Offline"} · Auto-Mode: ENABLED`}
      />

      <div className="flex-1 space-y-4 overflow-y-auto px-8 py-5">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <AccountCard account={account} />
          <RiskCard risk={risk} />
          <PerformanceCard performance={performance} />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <PriceChart symbol={priceSeries.symbol} series={priceSeries.points} />
          </div>
          <div className="space-y-4">
            <ConfluenceGauge confluence={confluence} />
            <EconomicCalendar calendar={calendar} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <PositionsTable positions={positions} />
          </div>
          <ExecutionLog logs={logs} />
        </div>
      </div>

      <Footer totalFloat={totalFloat} riskPerTradePct={risk.riskPerTradePct} />
    </div>
  );
}