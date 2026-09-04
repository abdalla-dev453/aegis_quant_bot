import React, { useEffect, useState } from "react";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: DashboardIcon },
  { key: "performance", label: "Performance Matrix", icon: MatrixIcon },
  { key: "strategy", label: "Strategy Builder", icon: StrategyIcon },
  { key: "logs", label: "Logs", icon: LogsIcon },
  { key: "settings", label: "Settings", icon: SettingsIcon },
];

const useClock = (timeZone) => {
  const [time, setTime] = useState(() => formatTime(timeZone));
  useEffect(() => {
    const id = setInterval(() => setTime(formatTime(timeZone)), 1000);
    return () => clearInterval(id);
  }, [timeZone]);
  return time;
};

const formatTime = (timeZone) => {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone,
  }).format(new Date());
};

export default function Sidebar({ activePage, onNavigate }) {
  const [isOpen, setIsOpen] = useState(false);
  const local = useClock(undefined);
  const utc = useClock("UTC");
  const nyMkt = useClock("America/New_York");

  // Helper function to handle navigation changes and automatically close sidebar on mobile
  const handleNav = (key) => {
    onNavigate(key);
    setIsOpen(false);
  };

  return (
    <>
      {/* 1. MOBILE TOP HEADER (Only visible on smaller screens) */}
      <div className="flex h-14 w-full items-center justify-between border-b border-border bg-surface px-4 md:hidden">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-bull-dim text-bull">
            <CheckIcon />
          </span>
          <span className="text-xs font-semibold tracking-wide text-ink">AEGIS QUANT</span>
        </div>
        
        {/* Animated Hamburger Trigger Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="relative z-50 flex h-8 w-8 flex-col items-center justify-center gap-1.5 rounded-md border border-border bg-surface-alt transition-colors hover:bg-white/[0.02]"
          aria-label="Toggle Menu"
        >
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-transform duration-300 ${isOpen ? "translate-y-2 rotate-45" : ""}`} />
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-opacity duration-300 ${isOpen ? "opacity-0" : ""}`} />
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-transform duration-300 ${isOpen ? "-translate-y-2 -rotate-45" : ""}`} />
        </button>
      </div>

      {/* 2. MOBILE DARK BACKGROUND BACKDROP SLIDEOVER (Fades in out smoothly) */}
      <div
        onClick={() => setIsOpen(false)}
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity duration-300 backdrop-blur-xs md:hidden ${
          isOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* 3. SIDEBAR COMPONENT (Fixed slide-in drawer on mobile, static on desktop) */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-full w-60 shrink-0 flex-col border-r border-border bg-surface transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Header */}
        <div className="flex items-center gap-2 px-5 pt-6 pb-5">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-bull-dim text-bull">
            <CheckIcon />
          </span>
          <div>
            <div className="text-sm font-semibold tracking-wide text-ink">AEGIS QUANT</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">Algo Engine v3.4.1</div>
          </div>
        </div>

        {/* Real-time clocks */}
        <div className="space-y-1 border-b border-border px-5 pb-5 font-mono text-[11px] text-ink-dim">
          <ClockRow label="Local" value={local} />
          <ClockRow label="UTC" value={utc} />
          <ClockRow label="NY MKT" value={nyMkt} />
        </div>

        {/* Active Engine Connections */}
        <div className="space-y-3 border-b border-border px-5 py-4">
          <StatusRow label="MT5 Connected" detail="Ping: 12ms" ok />
          <StatusRow label="AI Brain Sync" detail="Active · live" ok />
          <StatusRow label="News API" detail="Live feed" ok />
        </div>

        {/* Navigation Items (Smooth button animations) */}
        <nav className="flex-1 space-y-0.5 px-3 py-4">
          {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
            const active = key === activePage;
            return (
              <button
                key={key}
                onClick={() => handleNav(key)}
                className={`group flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-[13px] transition-all duration-200 ease-out border ${
                  active
                    ? "bg-accent/10 text-ink border-accent/30 shadow-xs"
                    : "text-ink-dim hover:bg-white/[0.03] hover:text-ink border-transparent hover:translate-x-0.5"
                }`}
              >
                <Icon active={active} />
                <span className="transition-colors duration-200">{label}</span>
              </button>
            );
          })}
        </nav>

        {/* Hardware Status Monitoring footer */}
        <div className="border-t border-border px-5 py-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-faint">System Health</div>
          <div className="flex gap-4 font-mono text-[11px] text-ink-dim">
            <span>CPU 24%</span>
            <span>MEM 42%</span>
            <span className="text-bull animate-pulse">NET OK</span>
          </div>
        </div>
      </aside>
    </>
  );
}

function ClockRow({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-faint">{label}</span>
      <span className="text-ink-dim tabular-nums">{value}</span>
    </div>
  );
}

function StatusRow({ label, detail, ok }) {
  return (
    <div className="flex items-start gap-2">
      <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full transition-all duration-500 ${ok ? "bg-bull shadow-[0_0_6px_#22d67e]" : "bg-bear shadow-[0_0_6px_#ff4d5e]"}`} />
      <div className="leading-tight">
        <div className="text-[12px] text-ink">{label}</div>
        <div className="text-[10px] text-ink-faint">{detail}</div>
      </div>
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function iconBase(active) {
  return `transition-colors duration-200 ${active ? "text-accent" : "text-ink-faint group-hover:text-ink-dim"}`;
}

function DashboardIcon({ active }) {
  return (
    <svg className={iconBase(active)} width="15" height="15" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="13" y="3" width="8" height="5" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="13" y="10" width="8" height="11" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function MatrixIcon({ active }) {
  return (
    <svg className={iconBase(active)} width="15" height="15" viewBox="0 0 24 24" fill="none">
      <path d="M4 19V9M12 19V5M20 19v-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function StrategyIcon({ active }) {
  return (
    <svg className={iconBase(active)} width="15" height="15" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="2.5" fill="currentColor" />
    </svg>
  );
}
function LogsIcon({ active }) {
  return (
    <svg className={iconBase(active)} width="15" height="15" viewBox="0 0 24 24" fill="none">
      <path d="M4 5h16M4 12h16M4 19h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function SettingsIcon({ active }) {
  return (
    <svg className={iconBase(active)} width="15" height="15" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
      <path d="M19.4 15a1.7 1.7 0 00.34 1.87l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.7 1.7 0 00-1.87-.34 1.7 1.7 0 00-1 1.55V21a2 2 0 11-4 0v-.09a1.7 1.7 0 00-1-1.55 1.7 1.7 0 00-1.87.34l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.7 1.7 0 00.34-1.87 1.7 1.7 0 00-1.55-1H3a2 2 0 110-4h.09a1.7 1.7 0 001.55-1 1.7 1.7 0 00-.34-1.87l-.06-.06a2 2 0 112.83-2.83l.06.06a1.7 1.7 0 001.87.34H9a1.7 1.7 0 001-1.55V3a2 2 0 114 0v.09a1.7 1.7 0 001 1.55 1.7 1.7 0 001.87-.34l.06-.06a2 2 0 112.83 2.83l-.06.06a1.7 1.7 0 00-.34 1.87V9a1.7 1.7 0 001.55 1H21a2 2 0 110 4h-.09a1.7 1.7 0 00-1.55 1z" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
