import { useEffect } from "react";
import { Helmet } from "react-helmet-async";

export default function PrivacyPolicy() {
  useEffect(() => {
    document.title = "Privacy Policy | Onyx FX";
  }, []);

  return (
    <>
      <Helmet>
        <title>Privacy Policy | Onyx FX</title>
        <meta name="description" content="Onyx FX Privacy Policy — How we collect, use, and protect your data." />
        <meta property="og:title" content="Privacy Policy | Onyx FX" />
        <meta property="og:description" content="How we collect, use, and protect your data." />
      </Helmet>

      <div className="flex min-h-screen flex-col">
        <header className="border-b border-border bg-surface px-4 py-4 md:px-8">
          <div className="mx-auto max-w-4xl">
            <a href="/" className="flex items-center gap-2 text-ink" onClick={(e) => { e.preventDefault(); window.history.back(); }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              <span className="text-sm font-semibold tracking-wide">Onyx FX</span>
            </a>
          </div>
        </header>

        <main className="flex-1 px-4 py-8 md:px-8">
          <div className="mx-auto max-w-3xl space-y-8">
            <div>
              <h1 className="text-2xl md:text-3xl font-semibold text-ink">Privacy Policy</h1>
              <p className="mt-2 text-sm text-ink-faint">Last updated: September 2026</p>
            </div>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">1. Data We Collect</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                Onyx FX is a locally-hosted algorithmic trading dashboard. We do not operate a cloud service,
                and we do not collect personal data from visitors. The only data processed by this application includes:
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li><strong>MT5 Credentials:</strong> Submitted via the Settings page to establish a local MT5 terminal connection. Credentials are held in memory for the session only and are never persisted to disk or transmitted to any third party.</li>
                <li><strong>Trading Data:</strong> Account equity, positions, P&L, and execution logs fetched from your local MT5 terminal via the FastAPI bridge. This data never leaves your machine/network.</li>
                <li><strong>Preferences:</strong> Theme selection (light/dark/system) and cookie consent stored in <code>localStorage</code> on your device.</li>
                <li><strong>AI Requests:</strong> Market context (price data, indicators, news headlines) sent to OpenAI's API when the AI engine is enabled. No account credentials or PII are included.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">2. How Data Is Used</h2>
              <ul className="ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>MT5 credentials: Used exclusively to initialize the MetaTrader 5 terminal connection for the current session.</li>
                <li>Trading data: Displayed in the dashboard for monitoring and analysis.</li>
                <li>Preferences: Persist your UI theme and consent choices across sessions.</li>
                <li>AI requests: Generate trade proposals based on technical and fundamental analysis.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">3. Data Sharing</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                We do not sell, rent, or share your data with third parties. The only external communication is:
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>OpenAI API (when AI engine is enabled) — receives anonymized market context only.</li>
                <li>News API (NewsAPI.org or Yahoo RSS) — public economic calendar data.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">4. Local Storage & Cookies</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                This application uses <code>localStorage</code> for:
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>Theme preference (light/dark/system)</li>
                <li>Cookie consent preferences</li>
              </ul>
              <p className="mt-2 text-sm text-ink-dim">
                No cookies are set by the application itself. You can clear all local data at any time via your browser settings.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">5. Security</h2>
              <ul className="ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>MT5 credentials are never written to disk or logs.</li>
                <li>API communication uses HTTPS in production (configure <code>CORS_ORIGINS</code> and <code>API_TOKEN</code>).</li>
                <li>The FastAPI bridge includes rate limiting and HMAC-based API key authentication.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">6. Your Rights</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                Since all data resides on your local machine, you have full control. You can:
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>Clear <code>localStorage</code> to remove preferences and consent.</li>
                <li>Stop the backend process to terminate all data processing.</li>
                <li>Revoke MT5 credentials by restarting the bot without providing them.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">7. Changes to This Policy</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                Updates will be posted here with a revised "Last updated" date. Continued use of the dashboard constitutes acceptance.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">8. Contact</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                Questions about this policy? Open an issue on the project repository or contact the maintainer.
              </p>
            </section>
          </div>
        </main>

        <footer className="border-t border-border px-4 py-6 md:px-8">
          <div className="mx-auto max-w-3xl text-center text-xs text-ink-faint">
            © 2026 Onyx FX · Algorithmic Trading Engine
          </div>
        </footer>
      </div>
    </>
  );
}