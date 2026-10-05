import { useState, useEffect } from "react";
import { api } from "../lib/api.js";

export default function RiskManagement() {
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [riskPerTrade, setRiskPerTrade] = useState("0.50");
  const [maxDailyLoss, setMaxDailyLoss] = useState("2.00");
  const [maxOpenPositions, setMaxOpenPositions] = useState(5);
  const [autoExecute, setAutoExecute] = useState(false);
  const [showAutoModal, setShowAutoModal] = useState(false);
  const [showKillModal, setShowKillModal] = useState(false);
  const [killConfirmInput, setKillConfirmInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    api.getDevices()
      .then((devs) => {
        setDevices(devs || []);
        if (devs && devs.length > 0) {
          setSelectedDeviceId(devs[0].id);
          setAutoExecute(devs[0].auto_execute);
        }
      })
      .catch(console.error);
  }, []);

  const handleSaveRisk = async () => {
    if (!selectedDeviceId) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.updateRiskProfile(selectedDeviceId, {
        risk_per_trade_pct: riskPerTrade,
        max_daily_loss_pct: maxDailyLoss,
        max_open_positions: parseInt(maxOpenPositions, 10),
        auto_execute: autoExecute,
      });
      setMsg({ type: "success", text: "Risk limits updated successfully. Synchronized to EA." });
    } catch (err) {
      setMsg({ type: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleToggleAuto = () => {
    if (!autoExecute) {
      setShowAutoModal(true);
    } else {
      setAutoExecute(false);
    }
  };

  const confirmEnableAuto = () => {
    setAutoExecute(true);
    setShowAutoModal(false);
  };

  const handleExecuteKill = async () => {
    if (killConfirmInput !== "CONFIRM KILL") return;
    try {
      await api.triggerKillSwitch();
      setAutoExecute(false);
      setShowKillModal(false);
      setKillConfirmInput("");
      setMsg({ type: "error", text: "KILL SWITCH TRIGGERED. All open positions flattened and trading paused." });
    } catch (err) {
      alert("Kill switch error: " + err.message);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-6 space-y-8">
      {/* Title */}
      <div className="border-b border-border pb-4">
        <h1 className="text-xl font-bold text-ink">Risk Envelope & Circuit Breakers</h1>
        <p className="mt-1 text-xs text-ink-dim">
          Configure dual-layer mathematical risk constraints and emergency execution halts.
        </p>
      </div>

      {msg && (
        <div
          className={`rounded-lg border p-4 text-xs ${
            msg.type === "success"
              ? "border-bull/40 bg-bull-dim/20 text-bull"
              : "border-bear/40 bg-bear-dim/20 text-bear font-semibold"
          }`}
        >
          {msg.text}
        </div>
      )}

      {/* Device Selector */}
      {devices.length > 1 && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-ink-dim">Target Terminal:</span>
          <select
            value={selectedDeviceId || ""}
            onChange={(e) => setSelectedDeviceId(e.target.value)}
            className="rounded border border-border bg-surface px-3 py-1.5 font-mono text-xs text-ink"
          >
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.broker} - {d.account_number_masked})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Grid: Limits & Automation Switch */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left Card: Risk Limits */}
        <div className="space-y-5 rounded-xl border border-border bg-surface p-6">
          <h2 className="text-sm font-bold text-ink uppercase tracking-wider">Per-Trade & Daily Loss Limits</h2>

          <div>
            <label className="block text-xs font-semibold text-ink">Max Risk Per Trade (%)</label>
            <p className="text-[11px] text-ink-dim">Percentage of equity at risk per position stop loss.</p>
            <input
              type="number"
              step="0.05"
              min="0.10"
              max="5.00"
              value={riskPerTrade}
              onChange={(e) => setRiskPerTrade(e.target.value)}
              className="mt-2 w-full rounded border border-border bg-canvas px-3 py-2 font-mono text-xs text-ink"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink">Max Daily Loss Floor (%)</label>
            <p className="text-[11px] text-ink-dim">EA halts all trading if cumulative daily loss reaches this threshold.</p>
            <input
              type="number"
              step="0.10"
              min="0.50"
              max="10.00"
              value={maxDailyLoss}
              onChange={(e) => setMaxDailyLoss(e.target.value)}
              className="mt-2 w-full rounded border border-border bg-canvas px-3 py-2 font-mono text-xs text-ink"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink">Max Concurrent Positions</label>
            <p className="text-[11px] text-ink-dim">Hard ceiling on open tickets across all currency pairs.</p>
            <input
              type="number"
              min="1"
              max="20"
              value={maxOpenPositions}
              onChange={(e) => setMaxOpenPositions(e.target.value)}
              className="mt-2 w-full rounded border border-border bg-canvas px-3 py-2 font-mono text-xs text-ink"
            />
          </div>

          <button
            onClick={handleSaveRisk}
            disabled={saving}
            className="w-full rounded-lg bg-accent py-2.5 text-xs font-bold text-white hover:bg-accent/90"
          >
            {saving ? "Saving Changes..." : "Save & Sync Risk Limits"}
          </button>
        </div>

        {/* Right Card: Auto Execution & Emergency Kill */}
        <div className="space-y-6">
          {/* Auto Execute Switch */}
          <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-ink">AI Auto-Execution Switch</h3>
                <p className="text-xs text-ink-dim">Allow terminal EA to automatically place qualifying signals</p>
              </div>
              <button
                onClick={handleToggleAuto}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoExecute ? "bg-bull" : "bg-surface-alt"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoExecute ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
            <div className="rounded bg-canvas p-3 text-[11px] text-ink-dim">
              <strong>Dual-Key Rule:</strong> Both the Cloud Auto-Execute switch and the MT5 EA on-chart switch must be active for orders to execute automatically.
            </div>
          </div>

          {/* EMERGENCY KILL SWITCH */}
          <div className="rounded-xl border border-bear/50 bg-bear-dim/10 p-6 space-y-4">
            <div>
              <h3 className="text-sm font-bold text-bear uppercase tracking-wider">Emergency Kill Switch</h3>
              <p className="mt-1 text-xs text-ink-dim">
                Immediately flattens all open positions on the MT5 terminal and terminates automated trading.
              </p>
            </div>
            <button
              onClick={() => setShowKillModal(true)}
              className="w-full rounded-lg bg-bear py-3 text-xs font-bold uppercase tracking-wider text-white hover:bg-bear/90 shadow-lg"
            >
              Trigger Emergency Kill Switch
            </button>
          </div>
        </div>
      </div>

      {/* Auto-Execute Confirmation Modal */}
      {showAutoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-ink">Enable Automated Execution?</h3>
            <p className="text-xs text-ink-dim leading-relaxed">
              By enabling AI auto-execution, your local MetaTrader 5 Expert Advisor will automatically place market orders within your configured risk envelope.
            </p>
            <div className="flex justify-end gap-3 pt-4">
              <button
                onClick={() => setShowAutoModal(false)}
                className="rounded-lg border border-border px-4 py-2 text-xs font-semibold text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={confirmEnableAuto}
                className="rounded-lg bg-bull px-5 py-2 text-xs font-bold text-black hover:bg-bull/90"
              >
                Confirm & Enable
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Kill Switch Confirmation Modal */}
      {showKillModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-md rounded-xl border border-bear/60 bg-surface p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-bear uppercase">Confirm Emergency Kill</h3>
            <p className="text-xs text-ink leading-relaxed">
              This action will immediately close all active positions and pause signal execution. Type <span className="font-mono text-bear font-bold">CONFIRM KILL</span> to proceed.
            </p>
            <input
              type="text"
              placeholder="CONFIRM KILL"
              value={killConfirmInput}
              onChange={(e) => setKillConfirmInput(e.target.value)}
              className="w-full rounded border border-bear/50 bg-canvas px-3 py-2 font-mono text-xs text-ink"
            />
            <div className="flex justify-end gap-3 pt-4">
              <button
                onClick={() => {
                  setShowKillModal(false);
                  setKillConfirmInput("");
                }}
                className="rounded-lg border border-border px-4 py-2 text-xs font-semibold text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                disabled={killConfirmInput !== "CONFIRM KILL"}
                onClick={handleExecuteKill}
                className="rounded-lg bg-bear px-5 py-2 text-xs font-bold uppercase text-white hover:bg-bear/90 disabled:opacity-40"
              >
                Flatten All Positions
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
