import { useEffect } from "react";
import { Helmet } from "react-helmet-async";

export default function TermsOfService() {
  useEffect(() => {
    document.title = "Terms of Service | Onyx FX";
  }, []);

  return (
    <>
      <Helmet>
        <title>Terms of Service | Onyx FX</title>
        <meta name="description" content="Onyx FX Terms of Service — Your use of the algorithmic trading dashboard." />
        <meta property="og:title" content="Terms of Service | Onyx FX" />
        <meta property="og:description" content="Your use of the algorithmic trading dashboard." />
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
              <h1 className="text-2xl md:text-3xl font-semibold text-ink">Terms of Service</h1>
              <p className="mt-2 text-sm text-ink-faint">Last updated: September 2026</p>
            </div>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">1. Acceptance of Terms</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                By accessing and using the Onyx FX algorithmic trading dashboard ("the Software"), you agree to be bound
                by these Terms of Service ("Terms"). If you do not agree, do not use the Software.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">2. Nature of the Software</h2>
              <ul className="ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>Onyx FX is a <strong>self-hosted, open-source</strong> trading dashboard and execution engine.</li>
                <li>It runs entirely on your infrastructure (local machine, VPS, or private network).</li>
                <li>There is no SaaS offering, no cloud backend operated by us, and no managed service.</li>
                <li>You are solely responsible for deployment, configuration, and operation.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">3. No Financial Advice</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                <strong>The Software does not provide financial, investment, or trading advice.</strong> All trading decisions,
                strategies, parameters, and risk settings are configured by you. AI-generated proposals are algorithmic
                outputs based on technical indicators and news sentiment — they are not recommendations. You alone bear
                responsibility for all trades executed through the Software.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">4. Risk Disclosure</h2>
              <ul className="ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>Trading foreign exchange, metals, and CFDs on margin carries a high level of risk.</li>
                <li>You may lose all or more than your initial deposit.</li>
                <li>Past performance (backtests, paper trading, or live history) does not guarantee future results.</li>
                <li>Automated execution can amplify losses during adverse market conditions, connectivity issues, or software errors.</li>
                <li>Test thoroughly in paper/demo mode before enabling live trading.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">5. License</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                The Software is provided under the MIT License. You are free to use, modify, and distribute it subject
                to the license terms. See the <code>LICENSE</code> file in the repository for full details.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">6. No Warranty</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
                LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.
                IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY,
                WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE
                SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">7. Third-Party Dependencies</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                The Software integrates with third-party services subject to their own terms:
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-sm text-ink-dim">
                <li>MetaTrader 5 (MetaQuotes) — terminal and API</li>
                <li>OpenAI API — AI trade proposals (optional)</li>
                <li>NewsAPI.org / Yahoo Finance RSS — economic calendar data</li>
                <li>Python packages (FastAPI, pandas, MetaTrader5, etc.) — their respective licenses apply</li>
              </ul>
              <p className="mt-2 text-sm text-ink-dim">
                You are responsible for complying with all third-party terms of service and licensing.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">8. Data & Privacy</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                See our <a href="/privacy" className="underline hover:text-accent">Privacy Policy</a> for details on data handling.
                In summary: no data leaves your infrastructure except optional AI requests to OpenAI and public news API calls.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">9. Indemnification</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                You agree to indemnify and hold harmless the authors and contributors from any claims, damages, losses,
                or expenses (including legal fees) arising from your use of the Software, including but not limited to
                trading losses, regulatory violations, or third-party claims.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">10. Governing Law</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                These Terms are governed by the laws of the jurisdiction where the Software is deployed, without regard
                to conflict of law principles. Disputes shall be resolved in the courts of that jurisdiction.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-medium text-ink">11. Changes</h2>
              <p className="text-sm text-ink-dim leading-relaxed">
                We may update these Terms at any time. Continued use after changes constitutes acceptance. Check this page periodically.
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