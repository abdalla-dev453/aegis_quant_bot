import React from "react";
import Panel from "./Panel.jsx";

function formatCountdown(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export default function EconomicCalendar({ calendar }) {
  return (
    <Panel title="Economic Calendar / Sentiment">
      {calendar.autoHaltActive && (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-warn/30 bg-warn-dim px-3 py-2">
          <WarnIcon />
          <div>
            <div className="text-[11px] font-medium uppercase tracking-wide text-warn">
              Auto-Halt Trigger Active
            </div>
            <div className="text-[11px] text-ink-dim">
              Execution pause in {formatCountdown(calendar.autoHaltEtaSeconds)}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between rounded-md border border-border bg-surface-alt px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="rounded bg-bear-dim px-1.5 py-0.5 text-[9px] font-semibold uppercase text-bear">
            {calendar.nextEvent.impact}
          </span>
          <div>
            <div className="text-[12px] text-ink">{calendar.nextEvent.name}</div>
            <div className="text-[10px] text-ink-faint">
              {calendar.nextEvent.currency} · {calendar.nextEvent.timeUtc} UTC
            </div>
          </div>
        </div>
        <span className="font-mono text-[11px] text-ink-dim">{calendar.nextEvent.minutesAway}m</span>
      </div>
    </Panel>
  );
}

function WarnIcon() {
  return (
    <svg className="mt-0.5 shrink-0 text-warn" width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}