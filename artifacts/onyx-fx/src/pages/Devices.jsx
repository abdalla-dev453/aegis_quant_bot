import { useState, useEffect } from "react";
import { api } from "../lib/api.js";

export default function Devices({ onNavigateOnboarding }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [renameText, setRenameText] = useState("");

  const loadDevices = async () => {
    try {
      const data = await api.getDevices();
      setDevices(data || []);
    } catch (err) {
      console.error("Failed to load devices:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDevices();
    const timer = setInterval(loadDevices, 5000);
    return () => clearInterval(timer);
  }, []);

  const handleRename = async (id) => {
    if (!renameText.trim()) return;
    try {
      await api.renameDevice(id, renameText.trim());
      setEditingId(null);
      await loadDevices();
    } catch (err) {
      alert("Rename failed: " + err.message);
    }
  };

  const handleRevoke = async (id) => {
    if (!confirm("Are you sure you want to revoke this MT5 terminal? The device token will be permanently destroyed."))
      return;
    try {
      await api.revokeDevice(id);
      await loadDevices();
    } catch (err) {
      alert("Revoke failed: " + err.message);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-6 space-y-6">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-bold text-ink">Paired MT5 Terminals</h1>
          <p className="mt-1 text-xs text-ink-dim">
            Manage authenticated Expert Advisor bridge instances and API security.
          </p>
        </div>
        <button
          onClick={onNavigateOnboarding}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/90"
        >
          + Pair New Terminal
        </button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-xs text-ink-dim">Loading paired terminals...</div>
      ) : devices.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface p-8 text-center space-y-3">
          <p className="text-xs text-ink-dim">No MT5 terminals are currently paired.</p>
          <button
            onClick={onNavigateOnboarding}
            className="rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/90"
          >
            Start Setup Wizard
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {devices.map((d) => (
            <div key={d.id} className="rounded-xl border border-border bg-surface p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  {editingId === d.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={renameText}
                        onChange={(e) => setRenameText(e.target.value)}
                        className="rounded border border-border bg-canvas px-2 py-1 font-mono text-xs text-ink"
                      />
                      <button
                        onClick={() => handleRename(d.id)}
                        className="rounded bg-accent px-2.5 py-1 text-xs font-semibold text-white"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs text-ink-dim"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <h3 className="font-bold text-sm text-ink">{d.name}</h3>
                      <button
                        onClick={() => {
                          setEditingId(d.id);
                          setRenameText(d.name);
                        }}
                        className="text-[10px] text-accent hover:underline"
                      >
                        rename
                      </button>
                    </>
                  )}
                  <span
                    className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                      d.presence === "ONLINE"
                        ? "bg-bull-dim/30 text-bull"
                        : d.presence === "STALE"
                        ? "bg-warn-dim/30 text-warn"
                        : "bg-surface-alt text-ink-dim"
                    }`}
                  >
                    {d.presence}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs text-ink-dim">
                  <span>Broker: {d.broker}</span>
                  <span>Server: {d.server}</span>
                  <span>Account: {d.account_number_masked}</span>
                  <span>Currency: {d.account_currency}</span>
                  <span>Leverage: 1:{d.leverage}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleRevoke(d.id)}
                  className="rounded border border-bear/40 bg-bear-dim/20 px-3 py-1.5 text-xs font-semibold text-bear hover:bg-bear-dim/40"
                >
                  Revoke Device
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
