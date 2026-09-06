import { useEffect, useState } from "react";
import Panel from "../components/Panel.jsx";
import TopBar from "../components/TopBar.jsx";
import { fetchSettings, saveCredentials } from "../lib/botFeed.js";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({
    login: "",
    password: "",
    server: "",
    terminal_path: "",
  });
  const [status, setStatus] = useState("Loading server settings...");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setSettings(data);
        setStatus("Ready");
      })
      .catch((error) => setStatus(error.message));
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setStatus("Connecting to MT5...");
    try {
      const result = await saveCredentials({
        ...form,
        login: Number(form.login),
        terminal_path: form.terminal_path || null,
      });
      setStatus(result.message);
      setForm({ ...form, password: "" });
      setSettings(await fetchSettings());
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col">
      <TopBar
        title="Settings"
        subtitle="Connection and server strategy configuration"
      />
      <div className="grid flex-1 gap-4 overflow-y-auto px-8 py-5 lg:grid-cols-2">
        <Panel title="MT5 account connection">
          <form onSubmit={submit} className="space-y-3">
            <Field
              label="Account login"
              type="number"
              value={form.login}
              onChange={(value) => setForm({ ...form, login: value })}
              required
            />
            <Field
              label="Password"
              type="password"
              value={form.password}
              onChange={(value) => setForm({ ...form, password: value })}
              required
            />
            <Field
              label="Broker server"
              value={form.server}
              onChange={(value) => setForm({ ...form, server: value })}
              placeholder="Broker-Demo"
              required
            />
            <Field
              label="Terminal path (optional)"
              value={form.terminal_path}
              onChange={(value) => setForm({ ...form, terminal_path: value })}
              placeholder="C:\\Program Files\\MetaTrader 5\\terminal64.exe"
            />
            <button
              disabled={saving}
              className="rounded-md bg-accent px-3 py-2 text-[12px] font-medium text-white disabled:cursor-wait disabled:opacity-60"
            >
              {saving ? "Connecting..." : "Connect MT5"}
            </button>
            <p className="text-[11px] leading-relaxed text-ink-faint">
              Credentials are sent to the server for this session only. The API
              does not return or persist the password. Use HTTPS or a private
              network before entering live credentials.
            </p>
            <div className="text-[11px] text-ink-dim">{status}</div>
          </form>
        </Panel>

        <Panel title="Effective server configuration">
          {settings ? (
            <div className="space-y-2 text-[12px]">
              <Row
                label="Credential status"
                value={
                  settings.credentialsConfigured
                    ? "Configured"
                    : "Not configured"
                }
              />
              <Row label="Symbols" value={settings.symbols.join(", ") || "-"} />
              <Row
                label="Trigger / bias"
                value={`${settings.timeframeTrigger} / ${settings.timeframeBias}`}
              />
              <Row
                label="Risk per trade"
                value={`${settings.riskPerTradePct}%`}
              />
              <Row
                label="ATR stop / target"
                value={`${settings.atrStopMultiplier} / ${settings.atrTakeProfitMultiplier}`}
              />
              <Row
                label="Max positions"
                value={settings.maxConcurrentPositions}
              />
              <Row label="Magic number" value={settings.magicNumber} />
            </div>
          ) : (
            <div className="text-[12px] text-ink-faint">{status}</div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Field({ label, type = "text", value, onChange, ...props }) {
  return (
    <label className="block text-[11px] text-ink-dim">
      {label}
      <input
        {...props}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-ink outline-none focus:border-accent"
      />
    </label>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2">
      <span className="text-ink-faint">{label}</span>
      <span className="font-mono text-ink">{value}</span>
    </div>
  );
}
