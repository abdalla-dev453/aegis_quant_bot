import { useState, useEffect } from "react";
import { api } from "../lib/api.js";

export default function Signals() {
  const [signals, setSignals] = useState([]);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [signalDetail, setSignalDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [dispatching, setDispatching] = useState(false);

  const fetchSignals = async () => {
    try {
      const data = await api.getSignals();
      setSignals(data || []);
      if (!selectedSignal && data && data.length > 0) {
        setSelectedSignal(data[0]);
      }
    } catch (err) {
      console.error("Failed to load signals:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedSignal) {
      api.getSignalDetail(selectedSignal.id)
        .then((detail) => setSignalDetail(detail))
        .catch(() => setSignalDetail({ signal: selectedSignal, events: [] }));
    }
  }, [selectedSignal]);

  const handleTestDispatch = async () => {
    setDispatching(true);
    try {
      const devices = await api.getDevices();
      if (devices && devices.length > 0) {
        await api.dispatchSignal(devices[0].id, "EURUSD", "BUY", "1.08500");
        await fetchSignals();
      }
    } catch (err) {
      alert("Dispatch failed: " + err.message);
    } finally {
      setDispatching(false);
    }
  };

  const filteredSignals = signals.filter((s) => {
    if (statusFilter === "ALL") return true;
    return s.state === statusFilter;
  });

  return (
    <div className="flex h-full flex-col md:flex-row overflow-hidden">
      {/* Left List: Live Signals Feed */}
      <div className="flex-1 flex flex-col border-r border-border overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border p-4">
          <div>
            <h1 className="text-base font-bold text-ink">AI Trade Signals Feed</h1>
            <p className="text-xs text-ink-dim">Realtime quantitative momentum & confluence models</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleTestDispatch}
              disabled={dispatching}
              className="rounded border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-semibold text-accent hover:bg-accent/20"
            >
              {dispatching ? "Dispatching..." : "+ Test Signal"}
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2 text-xs">
          {["ALL", "CREATED", "DELIVERED", "ACKED", "EXECUTED", "REJECTED"].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`rounded px-2.5 py-1 font-mono transition-colors ${
                statusFilter === st
                  ? "bg-accent text-white font-bold"
                  : "text-ink-dim hover:bg-surface-alt hover:text-ink"
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        {/* Feed List */}
        <div className="flex-1 divide-y divide-border overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-xs text-ink-dim">Loading signals...</div>
          ) : filteredSignals.length === 0 ? (
            <div className="p-8 text-center text-xs text-ink-dim">No signals match the selected filter.</div>
          ) : (
            filteredSignals.map((sig) => {
              const isSelected = selectedSignal?.id === sig.id;
              const isBuy = sig.action === "BUY";
              return (
                <div
                  key={sig.id}
                  onClick={() => setSelectedSignal(sig)}
                  className={`cursor-pointer p-4 transition-colors ${
                    isSelected ? "bg-surface-alt" : "hover:bg-surface/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-[11px] font-bold ${
                          isBuy ? "bg-bull-dim/40 text-bull" : "bg-bear-dim/40 text-bear"
                        }`}
                      >
                        {sig.action}
                      </span>
                      <span className="font-mono text-sm font-bold text-ink">{sig.symbol}</span>
                      <span className="text-xs text-ink-dim">@ {sig.reference_price}</span>
                    </div>

                    <span
                      className={`font-mono text-[10px] uppercase font-bold rounded px-2 py-0.5 ${
                        sig.state === "EXECUTED"
                          ? "bg-bull-dim/30 text-bull"
                          : sig.state === "REJECTED"
                          ? "bg-bear-dim/30 text-bear"
                          : "bg-surface text-ink-dim"
                      }`}
                    >
                      {sig.state}
                    </span>
                  </div>

                  <div className="mt-2 flex items-center justify-between text-xs font-mono text-ink-dim">
                    <div className="flex items-center gap-3">
                      <span>SL: {sig.stop_loss}</span>
                      <span>TP: {sig.take_profit}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="h-1.5 w-12 rounded-full bg-surface-alt overflow-hidden">
                        <div
                          className="h-full bg-accent"
                          style={{ width: `${parseFloat(sig.confidence) * 100}%` }}
                        />
                      </div>
                      <span className="text-ink">{(parseFloat(sig.confidence) * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right Drawer: AI Rationale & Execution Timeline */}
      {selectedSignal && (
        <div className="w-full md:w-[420px] shrink-0 border-l border-border bg-surface flex flex-col overflow-y-auto">
          <div className="border-b border-border p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-ink">Signal Analysis & Lifecycle</h2>
              <span className="font-mono text-[10px] text-ink-faint">
                {selectedSignal.id.slice(0, 8)}...
              </span>
            </div>
          </div>

          <div className="p-4 space-y-6 flex-1 overflow-y-auto">
            {/* Price Levels Card */}
            <div className="rounded-xl border border-border bg-canvas p-4">
              <div className="text-[11px] font-mono text-ink-dim uppercase">Execution Levels</div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center font-mono">
                <div className="rounded bg-surface p-2">
                  <div className="text-[10px] text-bear">STOP LOSS</div>
                  <div className="mt-1 text-xs font-bold text-ink">{selectedSignal.stop_loss}</div>
                </div>
                <div className="rounded bg-surface p-2 border border-accent/40">
                  <div className="text-[10px] text-accent">ENTRY</div>
                  <div className="mt-1 text-xs font-bold text-ink">{selectedSignal.reference_price}</div>
                </div>
                <div className="rounded bg-surface p-2">
                  <div className="text-[10px] text-bull">TAKE PROFIT</div>
                  <div className="mt-1 text-xs font-bold text-ink">{selectedSignal.take_profit}</div>
                </div>
              </div>
            </div>

            {/* AI Rationale Factors */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-ink">AI Decision Rationale</h3>
                <span className="font-mono text-[10px] text-accent">{selectedSignal.model_version}</span>
              </div>
              <p className="text-xs text-ink-dim leading-relaxed bg-canvas p-3 rounded-lg border border-border">
                {selectedSignal.rationale?.summary || "Confluence rules satisfied on timeframe."}
              </p>

              {/* Factors */}
              <div className="space-y-2">
                {(selectedSignal.rationale?.factors || []).map((f, i) => (
                  <div key={i} className="rounded-lg border border-border bg-canvas p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-ink">{f.name}</span>
                      <span className="font-mono text-[11px] text-accent">
                        {(parseFloat(f.weight) * 100).toFixed(0)}% weight
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-ink-dim">{f.description}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* State Machine Transition Timeline */}
            <div className="space-y-3 border-t border-border pt-4">
              <h3 className="text-xs font-bold text-ink">State Machine Lifecycle</h3>
              <div className="space-y-3 font-mono text-xs">
                {(signalDetail?.events || []).length === 0 ? (
                  <div className="text-ink-faint text-[11px]">Lifecycle recorded at backend.</div>
                ) : (
                  signalDetail.events.map((ev, i) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <div className="mt-1 h-2 w-2 rounded-full bg-accent shrink-0" />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-ink">{ev.to_state}</span>
                          <span className="text-[10px] text-ink-faint">via {ev.source}</span>
                        </div>
                        {ev.reason && (
                          <div className="text-[11px] text-bear mt-0.5">{ev.reason}</div>
                        )}
                        <div className="text-[10px] text-ink-faint">
                          {new Date(ev.occurred_at).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
