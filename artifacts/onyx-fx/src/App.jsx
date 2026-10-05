import { lazy, Suspense } from "react";
import { useLocation } from "wouter";
import Sidebar from "./components/Sidebar.jsx";
import CookieBanner from "./components/CookieBanner.jsx";
import MobileCTA from "./components/MobileCTA.jsx";
import { ThemeProvider } from "./lib/theme.js";
import { useBotFeed } from "./lib/useBotFeed.js";

const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Logs = lazy(() => import("./pages/Logs.jsx"));
const PerformanceMatrix = lazy(() => import("./pages/PerformanceMatrix.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const StrategyBuilder = lazy(() => import("./pages/StrategyBuilder.jsx"));
const PrivacyPolicy = lazy(() => import("./pages/PrivacyPolicy.jsx"));
const TermsOfService = lazy(() => import("./pages/TermsOfService.jsx"));
const Signals = lazy(() => import("./pages/Signals.jsx"));
const RiskManagement = lazy(() => import("./pages/RiskManagement.jsx"));
const Devices = lazy(() => import("./pages/Devices.jsx"));
const Onboarding = lazy(() => import("./pages/Onboarding.jsx"));

const PAGES = {
  dashboard: Dashboard,
  performance: PerformanceMatrix,
  strategy: StrategyBuilder,
  logs: Logs,
  settings: Settings,
  privacy: PrivacyPolicy,
  terms: TermsOfService,
  signals: Signals,
  risk: RiskManagement,
  devices: Devices,
  onboarding: Onboarding,
};

export default function App() {
  const [location, navigate] = useLocation();
  const activePage = location.replace(/^\//, "").replace(/\/$/, "") || "dashboard";
  const setActivePage = (page) => navigate(page === "dashboard" ? "/" : `/${page}`);
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

        <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
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
      <MobileCTA />
      <CookieBanner />
    </ThemeProvider>
  );
}
