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
import { resetPeakDrawdownGuard } from "../lib/botFeed.js";
import {
  SkeletonStatCard,
  SkeletonChart,
  SkeletonGauge,
  SkeletonList,
  SkeletonTable,
} from "../components/SkeletonLoaders.jsx";

export default function Dashboard() {
  const { account, risk, performance, confluence, calendar, positions, priceSeries, logs, connected, loading } = useBotFeed();

  const totalFloat = positions.reduce((sum, p) => sum + p.pnl, 0);
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });
  const resetPeakGuard = async () => {
    try {
      await resetPeakDrawdownGuard();
    } catch (error) {
      console.error("Unable to reset peak drawdown guard", error);
    }
  };

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <TopBar
        title="Command Dashboard"
        subtitle={`${today} · ${connected ? "Feed Connected" : "Feed Offline"} · Auto-Mode: ENABLED`}
      />

      <div className="flex-1 space-y-4 overflow-y-auto px-8 py-5">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {loading.account ? (
            <SkeletonStatCard />
          ) : (
            <AccountCard account={account} />
          )}
          {loading.risk ? (
            <SkeletonStatCard />
          ) : (
            <RiskCard risk={risk} onResetPeakGuard={resetPeakGuard} />
          )}
          {loading.performance ? (
            <SkeletonStatCard />
          ) : (
            <PerformanceCard performance={performance} />
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {loading.priceSeries ? (
              <SkeletonChart height={320} />
            ) : (
              <PriceChart symbol={priceSeries.symbol} series={priceSeries.points} />
            )}
          </div>
          <div className="space-y-4">
            {loading.confluence ? (
              <SkeletonGauge />
            ) : (
              <ConfluenceGauge confluence={confluence} />
            )}
            {loading.calendar ? (
              <SkeletonList items={3} />
            ) : (
              <EconomicCalendar calendar={calendar} />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {loading.positions ? (
              <SkeletonTable rows={5} />
            ) : (
              <PositionsTable positions={positions} />
            )}
          </div>
          {loading.logs ? (
            <SkeletonList items={5} />
          ) : (
            <ExecutionLog logs={logs} />
          )}
        </div>
      </div>

      <Footer totalFloat={totalFloat} riskPerTradePct={risk.riskPerTradePct} />
    </div>
  );
}
