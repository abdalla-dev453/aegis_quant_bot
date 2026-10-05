import { useEffect, useState } from "react";
import { useBotFeed } from "../lib/useBotFeed.js";
import { saveCredentials } from "../lib/botFeed.js";

export default function MobileCTA() {
  const { connected, loading } = useBotFeed();
  const [showConnect, setShowConnect] = useState(false);
  const [form, setForm] = useState({ login: "", password: "", server: "" });
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  // Only show on mobile
  useEffect(() => {
    const checkMobile = () => {
      setShowConnect(window.innerWidth < 768 && !connected);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, [connected]);

  const handleConnect = async (e) => {
    e.preventDefault();
    if (!form.login || !form.password || !form.server) {
      setStatus("Please fill in all fields");
      return;
    }
    setSaving(true);
    setStatus("Connecting...");
    try {
      await saveCredentials({
        ...form,
        login: Number(form.login),
      });
      setStatus("Connected!");
      setForm({ login: "", password: "", server: "" });
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (!showConnect) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 animate-slide-up pb-safe-bottom md:hidden">
      <div className="bg-surface border-t border-border shadow-mobile-cta">
        <div className="px-4 py-3 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${connected ? "bg-bull" : "bg-bear"}`} />
              <span className="text-sm font-medium text-ink">
                {connected ? "MT5 Connected" : "MT5 Disconnected"}
              </span>
            </div>
            <button
              onClick={() => setShowConnect(false)}
              className="text-ink-faint hover:text-ink"
              aria-label="Dismiss"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {!connected ? (
            <form onSubmit={handleConnect} className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="number"
                  placeholder="Login"
                  value={form.login}
                  onChange={(e) => setForm({ ...form, login: e.target.value })}
                  className="col-span-2 rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-ink outline-none focus:border-accent"
                  required
                />
                <input
                  type="text"
                  placeholder="Server"
                  value={form.server}
                  onChange={(e) => setForm({ ...form, server: e.target.value })}
                  className="rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-ink outline-none focus:border-accent"
                  required
                />
              </div>
              <input
                type="password"
                placeholder="Password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-ink outline-none focus:border-accent"
                required
              />
              <button
                type="submit"
                disabled={saving}
                className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:cursor-wait disabled:opacity-60"
              >
                {saving ? "Connecting..." : "Connect MT5"}
              </button>
              {status && <p className="text-[11px] text-center text-ink-dim">{status}</p>}
            </form>
          ) : (
            <div className="flex gap-2">
              <button
                className="flex-1 rounded-md border border-bear/30 bg-bear-dim px-3 py-2 text-sm font-medium text-bear"
                onClick={() => setShowConnect(true)}
              >
                Reconnect
              </button>
              <button
                className="flex-1 rounded-md border border-border bg-surface-alt px-3 py-2 text-sm font-medium text-ink"
              >
                Settings
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}