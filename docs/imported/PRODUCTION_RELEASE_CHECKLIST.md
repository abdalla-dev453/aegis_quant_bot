# Aegis Quant Production Release Checklist

**Status as of 2026-10-02: NOT APPROVED for funded/live execution.** This is a release gate, not a declaration that the checks have passed. No owner approval, MetaEditor build, broker test, Strategy Tester report, or supervised demo evidence was supplied to this workspace.

## Release Candidate

- **Qualification candidate:** `mt5/AegisConfluenceEA.mq5` only. It is the repository's preferred multi-timeframe EA scaffold and is the only path to qualify for this release.
- **Not in this release:** root `AegisQuantEA.mq5` and the Python runner. Do not run either in parallel with the candidate on the same account/symbol. Python paper tests do not qualify the EA or broker execution.
- **Build status:** source reviewed; no successful MetaEditor compile or `.ex5` artifact/hash is present. Candidate is not yet a releasable binary.
- **Hard rule:** no live account attachment until every required gate below has evidence, the account owner signs the limits and position policy, and the exact tested source/build/settings are frozen and hashed.

## Risk Profile And Owner Approval

No numeric limit in this file is an account-owner approval. The EA defaults are source defaults, not approved limits. Obtain a signed, dated profile before testing; use the same values in the final Strategy Tester and demo configuration.

| Limit / policy | Owner-approved value | EA configuration or evidence |
| --- | --- | --- |
| Account login, broker/server, account mode (hedging/netting) | Pending | Account identity screenshot/record; mask credentials |
| Allowed symbol(s) and trading sessions | Pending | `InpSymbol`, broker symbol specification |
| Risk per trade (% equity) | Pending | `InpRiskPerTradePct` |
| Daily loss/drawdown threshold and reset timezone | Pending | `InpMaxDailyDrawdownPct`; document server-day baseline behavior |
| Maximum aggregate open stop-loss risk | Pending | Not implemented in candidate; must be implemented and tested before live |
| Maximum concurrent positions | Pending | `InpMaxConcurrentPositions` |
| Maximum trades per day / consecutive losses | Pending | Not implemented in candidate; decision and enforcement required before live |
| Peak/weekly loss limits and re-arm authority | Pending | Not implemented/persisted in candidate; decision and enforcement required before live |
| Spread, slippage and gap limits | Pending | `InpMaxSpreadPoints`, `InpDeviationPoints`; post-fill policy also required |
| News/rollover/weekend blackout and open-position policy | Pending | Calendar/manual timestamp behavior must be tested; position policy must be signed |
| On any loss guard, outage, or kill switch: hold or close positions | Pending | Candidate does not automatically liquidate; document operator procedure |
| Maximum pilot capital / notional and maximum daily loss in currency | Pending | External broker/account limit plus operator-approved cap |

The EA currently has an in-memory daily baseline, default 1% per-trade risk, default 3% daily drawdown block, and a position-count limit. These are not durable across EA removal/restart, do not provide aggregate open-risk protection, and must not be represented as complete account safeguards. Changing inputs does not add missing controls.

## Gate 1: Source And Build

- [ ] Choose and record exact source revision; confirm only the confluence EA is in the candidate package.
- [ ] Compile on the target Windows MetaEditor build with zero errors and no unexplained warnings; retain compiler version, complete log, source hash, and `.ex5` hash.
- [ ] Resolve and test asynchronous request/pending/partial-fill reconciliation; do not enable async execution until order identity and restart recovery are proven.
- [ ] Normalize entry, SL, TP, and trailing prices to broker tick size (not just decimal digits); validate volume and risk after normalization.
- [ ] Add account identity/mode checks and a hard maximum aggregate stop-loss-risk gate; test both hedging and netting if both are in scope.
- [ ] Persist daily/peak/weekly loss state and require explicit operator re-arm after a trip; test terminal restart and EA re-attach.
- [ ] Add maximum trades/consecutive-loss limits and a durable, independent entry kill control, or record an explicit approved alternative that is enforced outside the EA.
- [ ] Make calendar lookup failure/stale data behavior fail closed for new entries; validate event currencies, coverage, and broker/server time.
- [ ] Verify all stop, freeze, spread, margin, session, filling-mode, reconnect, reject, timeout, and partial-fill paths against the target broker.

**Gate passes only when:** exact build compiles, high/critical code findings are closed, and all safety tests below pass on the selected broker/account mode. A clean compile alone is not a pass for order safety.

## Gate 2: Risk Approval And Strategy Tester

- [ ] Account owner signs the completed risk table above, allowed instruments, account mode, loss response, blackout policy, and pilot cap.
- [ ] Set the approved values in the version-controlled test record and EA inputs; retain a settings export/screenshot and its hash.
- [ ] Run deterministic checks for closed-candle signals, higher-timeframe data freshness, missing/invalid indicators, tick-size and lot-step boundaries, minimum-lot rejection, and all risk guards.
- [ ] Run MT5 Strategy Tester with realistic broker spread, commission, swaps, slippage, and execution delay across intended symbols and market regimes.
- [ ] Keep development/optimization and out-of-sample periods separate; record parameters, tester version, dates, data source, and report hash.
- [ ] Report trade count, expectancy, profit factor, Sharpe/Sortino, maximum drawdown, recovery factor, average win/loss, consecutive losses, monthly stability, and concentration.
- [ ] Run parameter sensitivity and Monte Carlo trade-order and cost perturbations. Document acceptance thresholds before reviewing results; do not infer future returns from backtest results.
- [ ] Reject the candidate for any unexplained look-ahead, unstable parameter dependence, or failed pre-agreed risk/performance threshold.

## Gate 3: Supervised Demo Trial

- [ ] Use a dedicated demo account matching intended broker, symbol specifications, and account mode; confirm account identity before enabling the EA.
- [ ] Complete at least one uninterrupted full market-week per intended broker/account configuration after the final code/settings freeze.
- [ ] Supervise and record startup, shutdown, re-attach, terminal/VPS restart, connection loss/recovery, stale quotes/history, high spread, market open/close, and news blackout.
- [ ] Exercise invalid stops, invalid volume, insufficient margin, market closed, requote, timeout, rejected order, partial fill, and cancellation/reconciliation paths.
- [ ] Trip every daily/weekly/peak/trade-count/aggregate guard, restart the terminal, and prove the halt remains active until authorized re-arm.
- [ ] Reconcile every order, deal, position, SL/TP change, and close against broker history and the EA audit log. No unexplained difference is acceptable.
- [ ] Prove an independent operator can disable new entries and carry out the approved open-position policy; verify an alert reaches the responsible operator.
- [ ] Save tester/demo reports, sanitized journals, broker history, configuration/source/build hashes, incident log, and operator sign-off.

**Restart the full demo qualification window** after a material code, risk, broker, symbol, or execution-setting change, or after any unresolved reconciliation/safety incident.

## Gate 4: Deployment Security And Operations

- [ ] Deploy the single tested artifact on a dedicated, patched, non-root host with restricted filesystem permissions and documented recovery access.
- [ ] Keep MT5 credentials and API keys in a secrets manager or protected environment file; do not commit credentials or expose them in frontend bundles, logs, tickets, or screenshots.
- [ ] Keep API services loopback/private behind authenticated TLS and an access-controlled gateway. CORS is not authorization. Do not expose the shared browser token as an operator identity boundary.
- [ ] Confirm network ACLs, firewall rules, TLS renewal, credential rotation, least privilege, disk/log rotation, time synchronization, backups, and host monitoring.
- [ ] Test alert delivery for disconnected terminal, rejected/partial order, loss-limit trip, EA stopped, log/disk failure, and unexpected account identity.
- [ ] Perform and document stop, rollback, restart, credential rotation, and recovery drills. Keep an operator on-call/contact roster and broker emergency-stop details.
- [ ] Confirm the machine, terminal, strategy instance, magic number, and account are single-owner; prevent duplicate instances and conflicting Python/EA/manual automation.

## Gate 5: Capped Pilot Authorization

All prior gates must pass before this gate starts. Live authorization is a separate, explicit owner decision; demo success alone is not authorization.

- [ ] Account owner signs a pilot authorization naming account, broker, symbols, exact source/build/settings hashes, capital/notional cap, monetary daily/total loss cap, dates, and responsible operator.
- [ ] Enforce the pilot cap at the broker/account boundary where possible. If a required cap cannot be enforced or independently monitored, do not start.
- [ ] Start with one approved symbol and the smallest practical size; add symbols only after a reviewed observation interval and renewed approval.
- [ ] Require active human supervision during the initial pilot. Review each fill, risk state, and alert on the agreed schedule.
- [ ] Stop new entries immediately on any unexpected order, guard bypass, mismatch, stale/unverified news state, missing audit record, account change, or loss threshold. Apply only the signed open-position policy.
- [ ] Hold at the pilot cap until a dated review accepts broker reconciliation, risk behavior, operational response, and performance evidence. Increase exposure only with written approval and a new release record.

## Current Closure Status

| Item | Status | Evidence / remaining action |
| --- | --- | --- |
| Sole qualification candidate named | Complete | `mt5/AegisConfluenceEA.mq5`; no other execution path is in this release |
| Python risk environment variables applied and validated | Complete for Python path only | `RISK_PER_TRADE_PCT`, `MAX_DAILY_LOSS_PCT`, `MAX_DRAWDOWN_FROM_PEAK_PCT`, `MAX_TRADES_PER_DAY`, `MAX_CONCURRENT_POSITIONS`, and related limits now load/validate at startup; regression tests added. This does not configure the EA. |
| Account-owner limits and pilot authorization | Blocked | Owner values/signature not supplied |
| EA compile and exact binary | Blocked | Requires Windows MetaEditor and target build |
| Broker/account controls and hard aggregate risk | Open, release-blocking | Candidate lacks complete account identity, durable aggregate-risk, and restart-safe loss controls |
| Partial-fill/idempotency and restart reconciliation | Open, release-blocking | Requires implementation plus broker-connected tests |
| Strategy Tester and robustness evidence | Blocked | No tester or reports available here |
| Full supervised demo week | Blocked | Requires demo account/operator and retained broker evidence |
| Host security, alert, and rollback drills | Blocked | Requires deployment environment and operator evidence |
| Capped live pilot | Not authorized | All preceding gates and signed owner authorization required |

## Release Decision

Current decision: **NO-GO for funded/live trading.** The repository unit tests and Python paper mode do not close the EA compile, broker execution, risk persistence, owner approval, strategy validation, security, or forward-demo gates. Do not change this decision based only on checklist completion or a calendar date; attach evidence for each gate and obtain named approval.
