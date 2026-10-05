import { useEffect, useRef, useState } from "react";
import { useTheme } from "../lib/theme.js";

export default function TopBar({ title, subtitle, control, setControl, onCloseAll, closeAllDisabled = false }) {
  const [confirmHalt, setConfirmHalt] = useState(false);
  const [confirmResume, setConfirmResume] = useState(false);
  const [haltError, setHaltError] = useState("");
  const [resumeError, setResumeError] = useState("");
  const [confirmCloseAll, setConfirmCloseAll] = useState(false);
  const [closeAllError, setCloseAllError] = useState("");
  const [closingAll, setClosingAll] = useState(false);
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const themeMenuRef = useRef(null);
  const { themeMode, setThemeMode } = useTheme();

  const status = control?.status ?? "RUNNING";
  const isRunning = status === "RUNNING";
  const isHalted = status === "HALTED";

  useEffect(() => {
    const closeMenu = (event) => {
      if (!themeMenuRef.current?.contains(event.target))
        setThemeMenuOpen(false);
    };
    document.addEventListener("pointerdown", closeMenu);
    return () => document.removeEventListener("pointerdown", closeMenu);
  }, []);

  const toggleLive = async () => {
    if (isHalted) {
      setResumeError("");
      setConfirmResume(true);
      return;
    }
    try {
      await setControl(isRunning ? "PAUSED" : "RUNNING", isRunning ? "Operator paused" : "Operator resumed");
    } catch (error) {
      console.error("Unable to update trading control", error);
    }
  };

  const resume = async () => {
    setResumeError("");
    try {
      await setControl("RUNNING", "Operator resumed after emergency halt");
      setConfirmResume(false);
    } catch (error) {
      setResumeError(error.message ?? "Unable to re-arm trading.");
    }
  };

  const halt = async () => {
    setHaltError("");
    try {
      await setControl("HALTED", "Emergency halt requested from dashboard");
      setConfirmHalt(false);
    } catch (error) {
      setHaltError(error.message ?? "Unable to halt trading.");
    }
  };

  const closeAll = async () => {
    setClosingAll(true);
    setCloseAllError("");
    try {
      const result = await onCloseAll();
      if (result.failed?.length) {
        throw new Error(`${result.closed.length} closed; ${result.failed.length} failed. Check the execution log.`);
      }
      setConfirmCloseAll(false);
    } catch (error) {
      setCloseAllError(error.message ?? "Unable to close bot-managed positions.");
    } finally {
      setClosingAll(false);
    }
  };

  return (
    <header className="relative z-50 flex flex-col gap-4 border-b border-border px-4 py-4 sm:px-6 sm:py-5 lg:flex-row lg:items-center lg:justify-between lg:px-8">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        <p className="mt-0.5 truncate text-[12px] text-ink-faint">{subtitle}</p>
      </div>

      <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:gap-3 lg:w-auto">
        <div ref={themeMenuRef} className="relative shrink-0">
          <button
            onClick={() => setThemeMenuOpen((open) => !open)}
            aria-expanded={themeMenuOpen}
            aria-haspopup="menu"
            aria-label="Choose theme"
            title="Choose theme"
            className="theme-control flex min-h-10 items-center gap-2 rounded-md border border-border bg-surface-alt px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-ink-dim transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:text-ink"
          >
            <span className="text-sm leading-none" aria-hidden="true">
              {themeMode === "light" ? "☼" : themeMode === "dark" ? "◐" : "◌"}
            </span>
            <span className="hidden sm:inline">{themeMode}</span>
          </button>

          {themeMenuOpen && (
            <div
              className="theme-menu absolute right-0 top-full z-60 mt-2 w-36 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-surface p-1.5 shadow-panel"
              role="menu"
            >
              {["light", "dark", "system"].map((mode) => (
                <button
                  key={mode}
                  onClick={() => {
                    setThemeMode(mode);
                    setThemeMenuOpen(false);
                  }}
                  role="menuitemradio"
                  aria-checked={themeMode === mode}
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-[11px] capitalize transition-colors ${themeMode === mode ? "bg-accent/10 text-accent" : "text-ink-dim hover:bg-surface-alt hover:text-ink"}`}
                >
                  {mode}
                  {themeMode === mode && <span aria-hidden="true">✓</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={toggleLive}
          className={`flex min-h-10 shrink-0 items-center gap-1.5 rounded-md border px-3 py-2 text-[11px] font-medium uppercase tracking-wide transition-all duration-200 hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 ${
            isRunning
              ? "border-bull/30 bg-bull-dim text-bull"
              : "border-border bg-surface-alt text-ink-faint"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${isRunning ? "bg-bull" : "bg-ink-faint"}`}
          />
          <span className="hidden sm:inline">
            {isRunning ? "Entries Enabled" : status === "PAUSED" ? "Paused" : "Re-arm Trading"}
          </span>
          <span className="sm:hidden">{isRunning ? "RUNNING" : status}</span>
        </button>

        <button
          onClick={() => { setHaltError(""); setConfirmHalt(true); }}
          disabled={isHalted}
          className="min-h-10 shrink-0 rounded-md border border-bear/30 bg-bear-dim px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-bear transition-all duration-200 hover:-translate-y-0.5 hover:bg-bear/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="hidden sm:inline">Emergency Halt</span>
          <span className="sm:hidden">Halt</span>
        </button>
        {onCloseAll && (
          <button
            onClick={() => { setCloseAllError(""); setConfirmCloseAll(true); }}
            disabled={closeAllDisabled || closingAll}
            className="min-h-10 shrink-0 rounded-md border border-bear/30 bg-bear-dim px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-bear transition-colors hover:bg-bear/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Close bot positions
          </button>
        )}
      </div>

      {confirmHalt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-80 rounded-lg border border-border bg-surface p-5">
            <div className="text-sm font-semibold text-ink">
              Confirm emergency halt
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-ink-dim">
              This stops new entries and automated position management. Open positions stay open; use Close bot positions to request market closes.
            </p>
            {haltError && <p role="alert" className="mt-3 text-[12px] text-bear">{haltError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmHalt(false)}
                className="rounded-md px-3 py-1.5 text-[12px] text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={halt}
                className="rounded-md bg-bear px-3 py-1.5 text-[12px] font-medium text-white hover:bg-bear/90"
              >
                Halt trading
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmResume && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5">
            <div className="text-sm font-semibold text-ink">Re-arm trading?</div>
            <p className="mt-2 text-[12px] leading-relaxed text-ink-dim">
              This restores automated position management. New entries can be sent only when the server execution mode is LIVE.
            </p>
            {resumeError && <p role="alert" className="mt-3 text-[12px] text-bear">{resumeError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmResume(false)}
                className="rounded-md px-3 py-1.5 text-[12px] text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={resume}
                className="rounded-md bg-bull px-3 py-1.5 text-[12px] font-medium text-white hover:bg-bull/90"
              >
                Re-arm
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmCloseAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5">
            <div className="text-sm font-semibold text-ink">Close bot-managed positions?</div>
            <p className="mt-2 text-[12px] leading-relaxed text-ink-dim">
              This sends market close orders for all positions managed by Aegis Quant. Other account positions are untouched.
            </p>
            {closeAllError && <p role="alert" className="mt-3 text-[12px] text-bear">{closeAllError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmCloseAll(false)}
                disabled={closingAll}
                className="rounded-md px-3 py-1.5 text-[12px] text-ink-dim hover:text-ink disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={closeAll}
                disabled={closingAll}
                className="rounded-md bg-bear px-3 py-1.5 text-[12px] font-medium text-white hover:bg-bear/90 disabled:opacity-50"
              >
                {closingAll ? "Closing..." : "Close positions"}
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
