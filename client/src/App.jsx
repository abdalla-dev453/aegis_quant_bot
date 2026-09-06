import { lazy, Suspense, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import { ThemeProvider } from "./lib/theme.js";
import { useBotFeed } from "./lib/useBotFeed.js";

const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Logs = lazy(() => import("./pages/Logs.jsx"));
const PerformanceMatrix = lazy(() => import("./pages/PerformanceMatrix.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const StrategyBuilder = lazy(() => import("./pages/StrategyBuilder.jsx"));

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
    <ThemeProvider>
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-canvas text-ink md:flex-row">
        <Sidebar
          activePage={activePage}
          onNavigate={setActivePage}
          connected={connected}
        />

        <main className="flex-1 overflow-y-auto">
          <Suspense
            fallback={
              <div className="page-transition p-6 text-sm text-ink-dim">
                Loading view...
              </div>
            }
          >
            <div key={activePage} className="page-transition h-full">
              <Page />
            </div>
          </Suspense>
        </main>
      </div>
    </ThemeProvider>
  );
}
