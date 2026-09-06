import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import { useBotFeed } from "./lib/useBotFeed.js";
import Dashboard from "./pages/Dashboard.jsx";
import Logs from "./pages/Logs.jsx";
import PerformanceMatrix from "./pages/PerformanceMatrix.jsx";
import Settings from "./pages/Settings.jsx";
import StrategyBuilder from "./pages/StrategyBuilder.jsx";

const PAGES = {
  dashboard: Dashboard,
  performance: PerformanceMatrix,
  strategy: StrategyBuilder,
  logs: Logs,
  settings: Settings,
};

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const { connected } = useBotFeed();
  const Page = PAGES[activePage] ?? Dashboard;

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-canvas text-ink md:flex-row">
      {/* Responsive navigation hub */}
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        connected={connected}
      />

      {/*
        Scrollable main view panel.
        - flex-1: Fills the remaining space.
        - overflow-y-auto: Allows scrollbars only within this container when content extends.
      */}
      <main className="flex-1 overflow-y-auto">
        <Page />
      </main>
    </div>
  );
}
