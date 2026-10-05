import React, { useEffect, useState } from "react";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: DashboardIcon },
  { key: "signals", label: "AI Signals", icon: SignalsIcon },
  { key: "risk", label: "Risk & Limits", icon: RiskIcon },
  { key: "devices", label: "MT5 Terminals", icon: DevicesIcon },
  { key: "performance", label: "Performance", icon: MatrixIcon },
  { key: "onboarding", label: "Pair Terminal", icon: PairIcon },
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

export default function Sidebar({ activePage, onNavigate, connected = false }) {
  const [isOpen, setIsOpen] = useState(false);
  const local = useClock(undefined);
  const utc = useClock("UTC");
  const nyMkt = useClock("America/New_York");

  const handleNav = (key) => {
    onNavigate(key);
    setIsOpen(false);
  };

  return (
    <>
      {/* Mobile Header */}
      <div className="flex h-14 w-full items-center justify-between border-b border-border bg-surface px-4 md:hidden">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-accent text-white font-bold text-[10px]">
            AQ
          </span>
          <span className="text-xs font-semibold tracking-wide text-ink">AegisQuant</span>
        </div>

        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex h-8 w-8 flex-col items-center justify-center gap-1.5 rounded-md border border-border bg-surface-alt"
          aria-label="Toggle Menu"
        >
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-transform duration-300 ${isOpen ? "translate-y-2 rotate-45" : ""}`} />
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-opacity duration-300 ${isOpen ? "opacity-0" : ""}`} />
          <span className={`h-0.5 w-4 rounded-full bg-ink transition-transform duration-300 ${isOpen ? "-translate-y-2 -rotate-45" : ""}`} />
        </button>
      </div>

      {/* Mobile Backdrop */}
      <div
        onClick={() => setIsOpen(false)}
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity duration-300 backdrop-blur-xs md:hidden ${
          isOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Sidebar Component */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-full w-60 shrink-0 flex-col border-r border-border bg-surface transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Header */}
        <div className="flex items-center gap-2 px-5 pt-6 pb-5">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-accent font-mono text-xs font-bold text-white">
            AQ
          </div>
          <div>
            <div className="text-xs font-bold tracking-tight text-ink">AegisQuant</div>
            <div className="text-[10px] font-mono text-ink-dim">EA Bridge v2.0</div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
            const active = activePage === key;
            return (
              <button
                key={key}
                onClick={() => handleNav(key)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                  active
                    ? "bg-accent text-white font-semibold shadow"
                    : "text-ink-dim hover:bg-surface-alt hover:text-ink"
                }`}
              >
                <Icon active={active} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>

        {/* Clocks & Status Footer */}
        <div className="border-t border-border p-4 space-y-3 font-mono text-[11px]">
          <div className="flex items-center justify-between text-ink-dim">
            <span>Server (UTC)</span>
            <span className="text-ink">{utc}</span>
          </div>
          <div className="flex items-center justify-between text-ink-dim">
            <span>NY Session</span>
            <span className="text-ink">{nyMkt}</span>
          </div>
          <div className="pt-2 border-t border-border flex items-center justify-between">
            <span className="text-ink-dim">Bridge State</span>
            <span className={`inline-flex items-center gap-1.5 font-bold ${connected ? "text-bull" : "text-warn"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-bull" : "bg-warn animate-pulse"}`} />
              {connected ? "LIVE" : "STANDBY"}
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}

// Minimal Icons (Pure JSX)
function DashboardIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  );
}

function SignalsIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
    </svg>
  );
}

function RiskIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}

function DevicesIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0H3" />
    </svg>
  );
}

function MatrixIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18h18" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-5 5-4-4-3 3" />
    </svg>
  );
}

function PairIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.6 6.6 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}
