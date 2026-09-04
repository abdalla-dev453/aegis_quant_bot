import React, { useState } from "react";

export default function TopBar({ title, subtitle }) {
  const [live, setLive] = useState(true);
  const [confirmHalt, setConfirmHalt] = useState(false);

  return (
    <header className="flex items-center justify-between border-b border-border px-8 py-5">
      <div>
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        <p className="mt-0.5 text-[12px] text-ink-faint">{subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => setLive((v) => !v)}
          className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide transition-colors ${
            live
              ? "border-bull/30 bg-bull-dim text-bull"
              : "border-border bg-surface-alt text-ink-faint"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-bull" : "bg-ink-faint"}`} />
          {live ? "Live Trading" : "Paused"}
        </button>

        <button
          onClick={() => setConfirmHalt(true)}
          className="rounded-md border border-bear/30 bg-bear-dim px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-bear transition-colors hover:bg-bear/20"
        >
          Emergency Halt
        </button>
      </div>

      {confirmHalt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-80 rounded-lg border border-border bg-surface p-5">
            <div className="text-sm font-semibold text-ink">Confirm emergency halt</div>
            <p className="mt-2 text-[12px] leading-relaxed text-ink-dim">
              This closes no positions automatically, but stops the bot from opening or
              modifying any trade until you re-enable Live Trading.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmHalt(false)}
                className="rounded-md px-3 py-1.5 text-[12px] text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setLive(false);
                  setConfirmHalt(false);
                }}
                className="rounded-md bg-bear px-3 py-1.5 text-[12px] font-medium text-white hover:bg-bear/90"
              >
                Halt trading
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}