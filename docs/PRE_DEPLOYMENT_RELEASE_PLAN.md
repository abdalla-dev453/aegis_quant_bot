# Aegis Quant: selected execution path and release evidence

## Decision

The sole qualification candidate is `lib/trading-engine`, running beside a
desktop MT5 terminal on a dedicated Windows VPS. It has a deterministic
closed-candle H1/H4 EMA and RSI gate, ATR-based stops, AI proposals that cannot
override the deterministic gate, broker-aware sizing, account identity pins,
portfolio/risk checks, local controls, and a paper mode. The AI service is not
an independent execution authority.

Keep all standalone MQL5 EAs detached during qualification. Keep cloud bridge
signal dispatch disabled (`503 signal_engine_unavailable`). Vercel/Netlify may
host the dashboard; Railway/Render may host the bridge API, but neither is the
MT5 order executor.

## Implemented in source

- Durable signal intent keyed by symbol, closed-candle time, and direction is
  written before live `order_send`; the same intent cannot be submitted twice.
- Unknown broker outcomes and partial fills pause the engine. The intent ID is
  copied into the broker order comment. A credential-protected reconciliation
  endpoint records the operator's broker-history reference, and API re-arm is
  blocked while any intent is unresolved.
- Daily, weekly, peak, trade-count, aggregate-risk, spread, stop-distance,
  reward/risk, margin, account identity, and emergency kill controls are
  implemented in the Python engine. Persistent risk/control files must be
  secured, backed up, and recovered only after broker reconciliation.
- `scripts/backtest_python_strategy.py` provides a chronological train/OOS
  research run using explicit spread, slippage, commission, tick value, and
  volume metadata. It assumes stop-first when stop and target are both touched
  in one candle and does not model AI proposals, news, portfolio risk, or
  trailing-stop behavior.
- Dashboard/API and bridge deployability are described in
  [`PLATFORM_DEPLOYMENT.md`](PLATFORM_DEPLOYMENT.md).

## Required evidence still outstanding

Source implementation is not equivalent to deployment proof. The release is
**NO-GO for funded/live trading** until all of these are complete:

1. **Freeze a broker profile:** owner-approved account login/server/mode,
   symbols, sessions, risk limits, currency loss caps, position response,
   news policy, and operator/re-arm authority. Numeric defaults are not owner
   approval.
2. **Build and test the Windows runtime:** install on the target Windows MT5
   host, pin the exact source/config hash, exercise startup/restart, account
   mismatch, stale quotes, news outage, rejected/partial/ambiguous sends,
   residual orders, emergency kill, and reconciliation. Verify single process
   ownership and that no EA is attached.
3. **Generate historical evidence:** use broker-specific H1/H4 data and
   execution costs with the research runner, then validate findings in MT5
   Strategy Tester. Keep development and untouched out-of-sample periods
   separate; include sensitivity/Monte Carlo and the raw-data/report hashes.
   No dataset or performance report is included in this repository today.
4. **Complete a supervised demo week:** one target broker/account configuration,
   final code and settings. Reconcile every order, deal, position, modification,
   and close to broker history; save sanitized terminal/API logs and reports.
5. **Close operational security:** restrict the API to loopback/private network
   behind authenticated TLS, remove shared-token exposure from browser builds,
   secure and back up local state, and rehearse alerting, rollback, restart,
   credential rotation, and operator emergency procedures.
6. **Separate live authorization:** only the account owner can approve a capped
   pilot by signing the exact account, symbols, source/config hashes, capital
   and monetary loss caps, dates, and responsible operator after all prior
   evidence has passed.

## Backtest invocation

From the repository root, provide broker-exported CSVs and exact contract-cost
metadata. Example (replace every value with the target broker's specifications):

```bash
python3 scripts/backtest_python_strategy.py \
  --h1 /secure/data/EURUSD_H1.csv \
  --h4 /secure/data/EURUSD_H4.csv \
  --point 0.00001 --tick-size 0.00001 --tick-value 1.0 \
  --spread-points 12 --slippage-points 2 --commission-per-lot 3.5 \
  --output /secure/reports/EURUSD_backtest.json
```

The example values are placeholders, not recommendations. Retain the source
CSV hashes and the exact command with the generated report. The harness is an
initial screening tool, not a substitute for Strategy Tester or demo evidence.
