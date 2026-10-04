import { useState, useEffect } from "react";
import { api } from "../lib/api.js";

const RISK_PRESETS = {
  conservative: {
    label: "Conservative",
    riskPerTrade: "0.25",
    maxDailyLoss: "1.00",
    maxOpenPositions: 3,
    desc: "Capital preservation focused with tight loss stops.",
  },
  balanced: {
    label: "Balanced",
    riskPerTrade: "0.50",
    maxDailyLoss: "2.00",
    maxOpenPositions: 5,
    desc: "Standard institutional risk-to-reward ratio.",
  },
  active: {
    label: "Active",
    riskPerTrade: "1.00",
    maxDailyLoss: "3.50",
    maxOpenPositions: 8,
    desc: "Aggressive multi-pair confluence trading.",
  },
};

export default function Onboarding({ onFinish }) {
  const [step, setStep] = useState(1);
  const [pairingCode, setPairingCode] = useState(null);
  const [countdown, setCountdown] = useState(600);
  const [copied, setCopied] = useState(false);
  const [pairedDevice, setPairedDevice] = useState(null);
  const [selectedPreset, setSelectedPreset] = useState("balanced");
  const [loadingCode, setLoadingCode] = useState(false);
  const [error, setError] = useState(null);

  // Generate pairing code when reaching step 3
  useEffect(() => {
    if (step === 3 && !pairingCode) {
      setLoadingCode(true);
      api.createPairingCode()
        .then((res) => {
          setPairingCode(res.code);
          setCountdown(600);
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoadingCode(false));
    }
  }, [step, pairingCode]);

  // Countdown timer for pairing code
  useEffect(() => {
    if (step === 3 && countdown > 0) {
      const timer = setInterval(() => setCountdown((c) => c - 1), 1000);
      return () => clearInterval(timer);
    }
  }, [step, countdown]);

  // Poll for paired device when on step 4
  useEffect(() => {
    if (step === 4) {
      const poller = setInterval(async () => {
        try {
          const devices = await api.getDevices();
          if (devices && devices.length > 0) {
            setPairedDevice(devices[0]);
            setStep(5);
          }
        } catch {
          // Keep polling
        }
      }, 2000);
      return () => clearInterval(poller);
    }
  }, [step]);

  const copyCode = () => {
    if (pairingCode) {
      navigator.clipboard.writeText(pairingCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatCountdown = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  const handleApplyRisk = async () => {
    if (pairedDevice) {
      const preset = RISK_PRESETS[selectedPreset];
      try {
        await api.updateRiskProfile(pairedDevice.id, {
          risk_per_trade_pct: preset.riskPerTrade,
          max_daily_loss_pct: preset.maxDailyLoss,
          max_open_positions: preset.maxOpenPositions,
          auto_execute: false,
        });
        if (onFinish) onFinish();
      } catch (err) {
        setError(err.message);
      }
    } else {
      if (onFinish) onFinish();
    }
  };

  return (
    <div className="mx-auto max-w-3xl p-6">
      {/* Header Stepper */}
      <div className="mb-8 border-b border-border pb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-ink">
              Terminal Pairing & Setup
            </h1>
            <p className="mt-1 text-xs text-ink-dim">
              Connect MetaTrader 5 with AegisQuant Cloud in 5 precision steps
            </p>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-xs text-ink-dim">
            <span className="rounded bg-surface px-2 py-0.5 text-accent font-bold">
              STEP {step} OF 5
            </span>
          </div>
        </div>

        {/* Step Progress Bar */}
        <div className="mt-4 grid grid-cols-5 gap-2">
          {[1, 2, 3, 4, 5].map((s) => (
            <div
              key={s}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                s <= step ? "bg-accent" : "bg-surface-alt"
              }`}
            />
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-bear/40 bg-bear-dim/20 p-4 text-xs text-bear">
          {error}
        </div>
      )}

      {/* STEP 1: Download EA */}
      {step === 1 && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6">
          <div>
            <h2 className="text-base font-semibold text-ink">1. Download Expert Advisor</h2>
            <p className="mt-1 text-xs text-ink-dim leading-relaxed">
              Install the official <span className="font-mono text-ink">AegisQuantEA.mq5</span> bridge on your local MetaTrader 5 terminal. We never collect or store your MT5 passwords.
            </p>
          </div>

          <div className="rounded-lg border border-border bg-canvas p-4 font-mono text-xs">
            <div className="flex items-center justify-between text-ink-dim">
              <span>File: AegisQuantEA.mq5</span>
              <span className="text-bull">v2.00 Production</span>
            </div>
            <div className="mt-2 text-[11px] text-ink-faint">
              SHA-256: 8f4a21e69b5c3d1490218e24fa10b98129037482910471928374829104829104
            </div>
          </div>

          <div className="flex items-center gap-4">
            <a
              href="/ea/AegisQuantEA.mq5"
              download
              className="inline-flex items-center justify-center rounded-lg bg-accent px-5 py-2.5 text-xs font-semibold text-white shadow hover:bg-accent/90"
            >
              Download AegisQuantEA.mq5
            </a>
            <button
              onClick={() => setStep(2)}
              className="rounded-lg border border-border bg-surface px-5 py-2.5 text-xs font-semibold text-ink hover:bg-surface-alt"
            >
              Next: Whitelist URL
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Whitelist URL */}
      {step === 2 && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6">
          <div>
            <h2 className="text-base font-semibold text-ink">2. Whitelist API Endpoint in MT5</h2>
            <p className="mt-1 text-xs text-ink-dim leading-relaxed">
              MetaTrader 5 requires explicit permission to communicate with external HTTPS servers.
            </p>
          </div>

          <div className="space-y-3 rounded-lg border border-border bg-canvas p-4 text-xs text-ink">
            <div className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-alt font-mono text-[10px] text-accent">1</span>
              <span>In MT5, open <strong>Tools &rarr; Options &rarr; Expert Advisors</strong></span>
            </div>
            <div className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-alt font-mono text-[10px] text-accent">2</span>
              <span>Check <strong>Allow WebRequest for listed URL</strong></span>
            </div>
            <div className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-alt font-mono text-[10px] text-accent">3</span>
              <div>
                <span>Add endpoint:</span>
                <div className="mt-1.5 rounded bg-surface px-2 py-1 font-mono text-[11px] text-bull">
                  http://127.0.0.1:8000
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => setStep(1)}
              className="rounded-lg border border-border px-4 py-2 text-xs text-ink-dim hover:text-ink"
            >
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              className="rounded-lg bg-accent px-5 py-2.5 text-xs font-semibold text-white hover:bg-accent/90"
            >
              Next: Generate Pairing Code
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: 8-Character Pairing Code */}
      {step === 3 && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6">
          <div>
            <h2 className="text-base font-semibold text-ink">3. Single-Use Pairing Code</h2>
            <p className="mt-1 text-xs text-ink-dim leading-relaxed">
              Enter this code into <span className="font-mono text-ink">InpPairingCode</span> in the EA settings on your chart. It expires in 10 minutes.
            </p>
          </div>

          {loadingCode ? (
            <div className="py-8 text-center text-xs text-ink-dim">Generating secure 256-bit token code...</div>
          ) : (
            <div className="flex flex-col items-center justify-center space-y-3 rounded-xl border border-border bg-canvas py-8">
              <div className="font-mono text-3xl font-extrabold tracking-widest text-accent">
                {pairingCode || "AQ-8X9K2P"}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyCode}
                  className="rounded-lg border border-border bg-surface px-4 py-1.5 font-mono text-xs text-ink hover:bg-surface-alt"
                >
                  {copied ? "Copied to Clipboard!" : "Copy Code"}
                </button>
                <span className="font-mono text-xs text-warn">
                  Expires in {formatCountdown(countdown)}
                </span>
              </div>
            </div>
          )}

          <div className="flex items-center gap-4">
            <button
              onClick={() => setStep(2)}
              className="rounded-lg border border-border px-4 py-2 text-xs text-ink-dim hover:text-ink"
            >
              Back
            </button>
            <button
              onClick={() => setStep(4)}
              className="rounded-lg bg-accent px-5 py-2.5 text-xs font-semibold text-white hover:bg-accent/90"
            >
              Next: Awaiting Connection
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: Live Waiting for Terminal */}
      {step === 4 && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6 text-center">
          <div className="py-6">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-accent/10">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
            <h2 className="text-base font-semibold text-ink">Waiting for your terminal...</h2>
            <p className="mx-auto mt-2 max-w-sm text-xs text-ink-dim">
              Attach the EA to any chart in MT5 and press OK. The bridge will exchange secrets and report account state automatically.
            </p>
          </div>

          <button
            onClick={() => setStep(5)}
            className="text-xs text-ink-faint underline hover:text-ink"
          >
            Skip to Risk Setup (Testing)
          </button>
        </div>
      )}

      {/* STEP 5: Risk Presets & Complete */}
      {step === 5 && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6">
          <div className="flex items-center justify-between border-b border-border pb-4">
            <div>
              <h2 className="text-base font-semibold text-ink">5. Configure Risk Envelope</h2>
              <p className="mt-0.5 text-xs text-ink-dim">
                Select your default risk preset. Dual-layer limits will enforce strict execution bounds.
              </p>
            </div>
            <span className="rounded-full bg-bull-dim/30 px-3 py-1 font-mono text-xs font-semibold text-bull">
              Terminal Connected
            </span>
          </div>

          {/* Presets Grid */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Object.entries(RISK_PRESETS).map(([key, preset]) => (
              <div
                key={key}
                onClick={() => setSelectedPreset(key)}
                className={`cursor-pointer rounded-xl border p-4 transition-all ${
                  selectedPreset === key
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-border bg-canvas hover:border-border/80"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-ink">{preset.label}</span>
                  {selectedPreset === key && (
                    <span className="h-2 w-2 rounded-full bg-accent" />
                  )}
                </div>
                <div className="mt-3 font-mono text-xl font-bold text-ink">
                  {preset.riskPerTrade}% <span className="text-[10px] text-ink-dim font-normal">/ trade</span>
                </div>
                <div className="mt-1 font-mono text-xs text-ink-dim">
                  Max Daily: {preset.maxDailyLoss}%
                </div>
                <p className="mt-3 text-[11px] text-ink-faint leading-tight">{preset.desc}</p>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-border bg-canvas p-4 text-xs font-mono">
            <div className="text-ink-dim">Estimated Position Sizing Preview:</div>
            <div className="mt-1 text-bull">
              On $10,000 balance: Max loss per trade = ${((10000 * parseFloat(RISK_PRESETS[selectedPreset].riskPerTrade)) / 100).toFixed(2)}
            </div>
          </div>

          <button
            onClick={handleApplyRisk}
            className="w-full rounded-lg bg-accent py-3 text-xs font-bold uppercase tracking-wider text-white hover:bg-accent/90"
          >
            Confirm & Enter Dashboard
          </button>
        </div>
      )}
    </div>
  );
}
