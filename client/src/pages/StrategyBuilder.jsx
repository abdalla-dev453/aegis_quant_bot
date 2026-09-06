import { useEffect, useState } from "react";
import Panel from "../components/Panel.jsx";
import TopBar from "../components/TopBar.jsx";
import { fetchSettings } from "../lib/botFeed.js";

const EMPTY = {
  symbols: [],
  timeframeTrigger: "H1",
  timeframeBias: "H4",
  riskPerTradePct: 0,
  atrStopMultiplier: 0,
  atrTakeProfitMultiplier: 0,
  maxConcurrentPositions: 0,
  magicNumber: "",
};

export default function StrategyBuilder() {
  const [settings, setSettings] = useState(EMPTY);
  const [status, setStatus] = useState("Loading server configuration...");
  const [draft, setDraft] = useState({ risk: "", stop: "", target: "" });

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setSettings(data);
        setDraft({
          risk: String(data.riskPerTradePct),
          stop: String(data.atrStopMultiplier),
          target: String(data.atrTakeProfitMultiplier),
        });
        setStatus("Connected to server configuration");
      })
      .catch((error) => setStatus(error.message));
  }, []);

  const validate = () => {
    const risk = Number(draft.risk);
    const stop = Number(draft.stop);
    const target = Number(draft.target);
    if (
      ![risk, stop, target].every(Number.isFinite) ||
      risk <= 0 ||
      risk > 5 ||
      stop <= 0 ||
      target <= 0
    ) {
      setStatus(
        "Invalid draft: risk must be 0-5%, and ATR values must be positive.",
      );
      return;
    }
    setStatus(
      `Draft valid. Server remains authoritative at ${settings.riskPerTradePct}% risk.`,
    );
  };

  return (
    <div className="flex min-h-full flex-col">
      <TopBar
        title="Strategy Builder"
        subtitle="Inspect and validate the live server strategy"
      />
      <div className="grid flex-1 gap-4 overflow-y-auto px-8 py-5 lg:grid-cols-2">
        <Panel title="Server-authoritative strategy">
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <Value
              label="Trigger timeframe"
              value={settings.timeframeTrigger}
            />
            <Value label="Bias timeframe" value={settings.timeframeBias} />
            <Value label="Symbols" value={settings.symbols.join(", ") || "-"} />
            <Value label="Magic number" value={settings.magicNumber || "-"} />
            <Value
              label="Max positions"
              value={settings.maxConcurrentPositions}
            />
            <Value
              label="Risk per trade"
              value={`${settings.riskPerTradePct}%`}
            />
          </div>
          <p className="mt-4 border-t border-border pt-3 text-[11px] leading-relaxed text-ink-faint">
            Entries require H1/H4 EMA agreement, rising or falling RSI
            confirmation, ATR stops, and sentiment confirmation. This screen
            does not silently override the running worker.
          </p>
        </Panel>

        <Panel title="Parameter validation">
          <div className="space-y-3">
            <Field
              label="Risk per trade (%)"
              value={draft.risk}
              onChange={(value) => setDraft({ ...draft, risk: value })}
            />
            <Field
              label="ATR stop multiplier"
              value={draft.stop}
              onChange={(value) => setDraft({ ...draft, stop: value })}
            />
            <Field
              label="ATR target multiplier"
              value={draft.target}
              onChange={(value) => setDraft({ ...draft, target: value })}
            />
            <button
              onClick={validate}
              className="rounded-md bg-accent px-3 py-2 text-[12px] font-medium text-white hover:bg-accent/90"
            >
              Validate draft
            </button>
            <div className="text-[11px] text-ink-faint">{status}</div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Value({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-surface-alt p-3">
      <div className="text-[10px] uppercase tracking-wide text-ink-faint">
        {label}
      </div>
      <div className="mt-1 font-mono text-ink">{value}</div>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <label className="block text-[11px] text-ink-dim">
      {label}
      <input
        type="number"
        step="0.1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-ink outline-none focus:border-accent"
      />
    </label>
  );
}
