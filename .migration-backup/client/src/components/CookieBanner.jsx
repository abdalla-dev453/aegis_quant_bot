import { useEffect, useState } from "react";

export default function CookieBanner() {
  const [show, setShow] = useState(false);
  const [preferences, setPreferences] = useState({
    necessary: true,
    analytics: false,
    marketing: false,
  });

  useEffect(() => {
    const consent = localStorage.getItem("cookieConsent");
    if (!consent) {
      setShow(true);
    } else {
      try {
        setPreferences(JSON.parse(consent));
      } catch {
        setShow(true);
      }
    }
  }, []);

  const acceptAll = () => {
    const consent = { necessary: true, analytics: true, marketing: true };
    localStorage.setItem("cookieConsent", JSON.stringify(consent));
    setPreferences(consent);
    setShow(false);
  };

  const acceptNecessary = () => {
    const consent = { necessary: true, analytics: false, marketing: false };
    localStorage.setItem("cookieConsent", JSON.stringify(consent));
    setPreferences(consent);
    setShow(false);
  };

  const savePreferences = () => {
    const consent = { necessary: true, ...preferences };
    localStorage.setItem("cookieConsent", JSON.stringify(consent));
    setShow(false);
  };

  if (!show) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-surface/95 backdrop-blur-sm md:bottom-4 md:left-4 md:right-auto md:w-96 md:rounded-lg md:border md:shadow-panel"
      role="dialog"
      aria-label="Cookie consent"
    >
      <div className="p-4 md:p-5">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5 text-accent">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-ink">Cookie Preferences</h3>
            <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">
              We use cookies to ensure the dashboard functions correctly, analyze performance, and improve your experience. Necessary cookies cannot be disabled.
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-[12px] font-medium text-ink">Necessary</span>
              <p className="text-[10px] text-ink-faint">Required for core functionality (auth, session, preferences)</p>
            </div>
            <input type="checkbox" checked={preferences.necessary} disabled className="h-4 w-4 accent-accent" />
          </label>

          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-[12px] font-medium text-ink">Analytics</span>
              <p className="text-[10px] text-ink-faint">Help us understand usage to improve the dashboard</p>
            </div>
            <input
              type="checkbox"
              checked={preferences.analytics}
              onChange={(e) => setPreferences({ ...preferences, analytics: e.target.checked })}
              className="h-4 w-4 accent-accent"
            />
          </label>

          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-[12px] font-medium text-ink">Marketing</span>
              <p className="text-[10px] text-ink-faint">Personalized content and feature announcements</p>
            </div>
            <input
              type="checkbox"
              checked={preferences.marketing}
              onChange={(e) => setPreferences({ ...preferences, marketing: e.target.checked })}
              className="h-4 w-4 accent-accent"
            />
          </label>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            onClick={acceptAll}
            className="flex-1 rounded-md bg-accent px-3 py-2 text-[12px] font-medium text-white hover:bg-accent/90"
          >
            Accept All
          </button>
          <button
            onClick={savePreferences}
            className="flex-1 rounded-md border border-border bg-surface-alt px-3 py-2 text-[12px] font-medium text-ink hover:bg-white/[0.03]"
          >
            Save Preferences
          </button>
          <button
            onClick={acceptNecessary}
            className="flex-1 rounded-md border border-border bg-surface-alt px-3 py-2 text-[12px] font-medium text-ink-dim hover:bg-white/[0.03]"
          >
            Necessary Only
          </button>
        </div>

        <p className="mt-3 text-[10px] text-center text-ink-faint">
          <a href="/privacy" className="underline hover:text-accent">Privacy Policy</a> ·{" "}
          <a href="/terms" className="underline hover:text-accent">Terms of Service</a>
        </p>
      </div>
    </div>
  );
}