# Aegis Quant Production Readiness Audit

**Audit date:** 2026-10-02  
**Baseline revision:** `ce6da2d`; follow-up changes below are in the current worktree.  
**Verdict:** **NOT READY** for live trading. The code may be used for source-level research and controlled paper testing. Do not promote either EA or the Python runner to funded execution until the blockers and critical findings below are closed and evidenced.

## Implementation Follow-Up (2026-10-09)

The current worktree adds these code-level safety changes; they do not change the NO-GO verdict:

- The EA bridge signal provider no longer emits a default BUY, fixed 0.10 volume, or fabricated indicator rationale. Dispatch returns `503 signal_engine_unavailable` until qualified market data and a real strategy are wired in.
- Python live mode requires expected account login, server, demo/real mode, and hedging/netting mode pins; the connected account is checked before the connection is accepted.
- Python risk/control state is persisted atomically. A missing control-state file starts PAUSED; a persisted RUNNING control returns as PAUSED after restart; corrupt state aborts startup. Daily/weekly/peak guards, trade count, and their latches are retained.
- Python order placement now applies configurable spread and aggregate stop-risk caps and rounds protective prices to broker tick size. Stop-risk assessment blocks when existing managed exposure has unknown risk.
- Python partial fills and excessive post-fill slippage now persistently pause new entries; partial fills are surfaced with their actual broker result for reconciliation. This is a safety pause, not a complete pending/residual order reconciler.
- Python original stop distance is keyed by the stable MT5 position identifier and durably persisted; an unmappable or unpersistable fill pauses entries. A host-local kill marker blocks entries while preserving position management.
- The preferred MQL5 EA defaults to synchronous execution, requires expected login/server/margin-mode inputs, blocks real accounts unless explicitly enabled, rounds prices to tick size, fails closed on calendar lookup errors, checks managed aggregate stop risk, persists daily/weekly/peak loss state, and exposes an independent terminal kill global variable. Partial fills set the kill latch pending reconciliation; async is rejected at initialization.
- Local Python trading-engine suite: **116 passed, 1 upstream pandas-ta deprecation warning**. The isolated bridge-provider regression test passed (**1 passed**). Bridge integration test execution could not complete because its test fixture requires Redis at `127.0.0.1:6379`, and this workspace cannot open local sockets. Python syntax compilation passed. No MetaEditor, broker, Strategy Tester, demo, or live evidence was available.

Remaining release blockers include MQL5 compile proof, broker-tested account-mode and order paths, complete fill/order/position reconciliation and idempotency across restart, a qualified bridge signal engine, API production identity/security review, strategy performance evidence, and supervised demo qualification. No strategy profitability claim is made.

## Scope And Evidence Standard

Reviewed both MQL5 files, Python strategy/data/execution/AI/API/risk code, deployment templates, runbooks, security notes, and the unit tests. The preferred EA is `mt5/AegisConfluenceEA.mq5`; the root `AegisQuantEA.mq5` is a separate and materially less complete implementation. The Python runner is a third execution path; protections in one path do not carry over to the others.

This was a static source and documentation audit plus the repository pytest run. There is no MetaEditor compiler or MT5 terminal/broker available in this Linux workspace, and no tester, demo, live, fault-injection, or production-host runs were supplied. “Observed” below means code/document behavior, not a claimed runtime simulation. No profit or strategy-performance claim is substantiated by this repository.

## Follow-Up Implementation

Applied from the pasted security/code-quality audit after checking each claim against the current source:

- Portfolio analysis failures now carry an explicit error and CRITICAL state; `check_pre_trade_risk()` blocks immediately instead of interpreting a failed analysis as an empty, healthy portfolio.
- Python lot sizing now rejects a computed volume below the broker minimum rather than rounding risk upward to the minimum lot.
- Python symbol metadata now expires after five minutes, refreshing tick value, tick size, volume step and stop-level information without relying on a reconnect invalidation call.
- Added regression tests for risk-analysis failure, below-minimum sizing, SELL margin direction, metadata refresh, unavailable-news blocking, and the pending-order fake interface.

The following claims from the attachment were already fixed or do not match the current code and were not reintroduced: pending orders are counted with managed positions; SELL margin uses `ORDER_TYPE_SELL`; paper responses are not passed to `record_order()`; HOLD maps to no trade and has zero volume; portfolio pre-trade exceptions return blocked (the swallowed analysis exception was the indirect hole fixed above); empty API tokens are rejected by protected routes, including localhost; `.env` is git-ignored; broker credentials are only submitted from HTTPS except localhost; corrupt position state aborts startup; the ML predictor is opt-in, checks minimum class sample counts, and its EMA fallback reports 0.0 confidence; news warnings are supplied to the AI and the main loop explicitly blocks entry on a warning; the currency parser explicitly handles XAU/XAG; and the old `test_neutral_drift_allows_both_directions` assertion contradicted the current fail-closed sentiment policy.

At the time of that attachment, unresolved items included indices/custom instrument currency exposure parsing; live MT5 news/calendar capability and coverage; original-risk-to-position reconciliation; MT5 async pending/partial-fill reconciliation and compile proof; account identity/mode controls; external API token architecture; persistent control/risk latches; and production-grade alerting. Later source changes in this worktree address some of those items; the dated implementation update below identifies what remains open.

## Strategy Behavior

The detailed findings below document the baseline revision and should be read with the dated implementation follow-up above. Where a baseline issue is addressed in source, it remains open until runtime evidence is collected.

### Preferred MQL5 confluence EA

- Evaluates on a new H1 bar using `CopyBuffer` shifts 1 and 2: closed H1 candle for trigger RSI/EMA/ATR, prior closed H1 RSI for slope, and prior closed H4 candle for bias.
- Buy: buys enabled, H4 fast EMA > slow EMA, H1 fast EMA > slow EMA, H1 RSI in `[52,70)`, RSI rising.
- Sell: sells enabled, H4 fast EMA < slow EMA, H1 fast EMA < slow EMA, H1 RSI in `(30,48]`, RSI falling.
- One market deal only. No limit/stop-entry implementation. Entry filters include fully tradable symbol and spread <= `InpMaxSpreadPoints`; high-impact EA calendar events and optional manual event timestamp block new entries.
- SL distance is `max(ATR * 1.5, broker stop-level distance)` by default; TP distance is `max(ATR * 3, SL distance)`. Sizing targets `InpRiskPerTradePct` (default 1%) using equity and loss tick value, then floors to volume step. Below minimum lot is rejected; maximum is broker maximum capped by `InpMaxLot`.
- Position management runs on every tick before the entry guards. At >= `InpBreakevenR` (default 1R), it raises/lowers the stop toward breakeven and trails by `InpAtrTrailMult` (default 1.25 ATR). SL only moves in a favorable direction. TP is not dynamically changed.
- Daily, weekly and peak drawdown latches now persist via terminal global variables; the EA blocks new entries and continues managing open positions. These controls have not been compiler- or broker-tested. No daily flatten, max trades/day, consecutive-loss limit, or cross-symbol aggregate budget exists beyond managed stop-risk accounting.

### Root MQL5 EA

- H1 fast/slow EMA and RSI only; despite having an `InpBiasTF`, it does not create/read bias-timeframe indicators. Entry uses shift 0 (forming candle) for EMA/RSI/ATR, so signals can change within a bar. Long requires fast > slow and RSI `[52,70)`; short requires fast < slow and RSI `(30,48]`, subject to direction flags. Defaults disable shorts.
- Uses market orders only. SL/TP use ATR multipliers (1.5/3.0 by default); no trailing stop is implemented. It allows up to `InpMaxPositions` owned positions (default 3), with 1.5% equity risk per trade by default.
- Manual event timestamp only; no spread cap. The freeze-level test compares spread to freeze distance and can reject/allow for the wrong reason. It has no daily/weekly/peak loss guards or restart-persistent state.

### Python runner

- `get_rates()` starts at MT5 position 1, and indicator generation consumes the newest returned candle, so the ordinary Python H1/H4 frames exclude the forming candle. The last-seen H1 timestamp is in-memory only. Data is fetched concurrently but through a serialized MT5 lock; no explicit H4 age/alignment gate is applied.
- The deterministic strategy now permits BUY/SELL on H1/H4 EMA agreement and H1 RSI confirmation when sentiment is informational. Neutral news sentiment never authorizes direction. News source availability is a separate required-by-default gate, and high-impact events still block entries. The Python decision path can therefore produce directional proposals when its gates pass; broker execution remains unverified.
- AI proposes action, volume, SL and TP. Pydantic rejects extra fields and malformed values; proposal symbol and presence/orientation of stops are checked, and execution independently computes a risk-capped maximum volume and broker preflight. Confidence is not thresholded, proposed stop distance/reward ratio is not bounded by policy, and untrusted news text is placed in the system-message content. AI outage/malformed responses become HOLD; repeated *losses* do not open a circuit breaker.
- Python ATR SL/TP are generated when AI stops are not supplied. Original risk is now persisted under the stable deal position identifier; if fill-to-position mapping or persistence fails, entries are paused and the fill requires reconciliation. Existing positions can still use current stop distance as fallback where old state has no identifier mapping.

## Findings By Severity

### Blocker

1. **No successful compile or reproducible EA build is evidenced.** The designated EA's `OnTradeTransaction` compares `transaction.request_id`, which requires confirmation against the target MQL5 compiler/API; the root EA uses `ENUM_TIMEFRAME` and `CPositionInfo` without a visible class include, also requiring compile confirmation. MetaEditor was unavailable. Treat compilation and target-terminal tester execution as a hard gate; no `.ex5` build record was supplied.
2. **The Python deterministic gate prevents all entries with current built-in sentiment.** `analyze_market_sentiment()` always returns a zero score; the strategy requires a strict directional threshold. This contradicts descriptions of a functioning AI execution loop and means no funded acceptance can be inferred from Python paper/order tests.
3. **Live/demo account identity is not checked.** Python validates that credentials exist, but does not assert account trade mode/login/server is the operator-approved environment before enabling live orders. The EA likewise has no explicit demo-account guard. A mistaken live/demo credential selection is not prevented.
4. **Operator-facing risk configuration can silently differ from the documented values.** `PRODUCTION_DEPLOYMENT_GUIDE.md` lists risk environment variables, but `RiskConfig` does not read those variables; the shipped `.env.example` says the limits live in `server/config.py`. A deployment can appear configured while actually running defaults.
5. **Remote API authentication is not a production identity boundary when using the documented frontend.** Deployment instructions put `VITE_API_TOKEN` into the public browser bundle. Anyone who can retrieve the bundle can reuse the same token, including against authenticated control/reset endpoints. Use server-side user authentication/authorization or keep the API private behind an authenticated gateway; CORS is not access control.

### Critical

- **Python risk latches and operator control reset on process restart.** Daily baseline, daily trade count, peak equity/latch, and `runtime_state` control status are in-memory. Restart clears a HALTED/PAUSED status to RUNNING and rebuilds baselines from current equity; previous intraday losses, drawdown halt, and count are forgotten. The MQL confluence EA also resets its daily baseline on initialization.
- **Pending/ambiguous/partial fills are not safely reconciled across all paths.** Python rejects every result except `TRADE_RETCODE_DONE`; a partial fill may already create exposure but is treated as a rejected order and is not recorded as a fill. There is no durable per-candle idempotency or pending-order reconciliation. EA async mode counts positions but not pending requests before new entries, and has a single in-memory pending request slot.
- **No portfolio-wide hard maximum open risk.** Python has max concurrent positions, a simplistic configured correlation block, and an exposure estimator; no aggregate stop-loss risk budget is enforced at the final order boundary. Each trade can risk 1.5% and three concurrent positions can exceed an approved aggregate cap. The EA only has a count cap.
- **Critical loss and operational controls are incomplete.** No weekly loss or consecutive-loss guard in either EA or Python. The EA has only a non-persistent daily entry block. The Python peak guard is not persisted, and risk/control APIs do not establish durable, restart-safe state. Existing positions are not automatically liquidated on loss-guard activation, disconnection, or kill switch; that may be appropriate only if an explicit close/hold policy is approved and tested.
- **Price normalization does not guarantee broker tick-size alignment.** EA prices are normalized to decimal digits (root EA does not normalize); Python SL/TP use decimal digits. Decimal precision and tick size can differ. Python hardcodes IOC filling; the preferred EA selects a mode from flags, but neither has demonstrated operation against the intended broker execution modes.
- **News/provider failure and event data are not a verified news control.** EA fallback to an empty calendar result is fail-open for entries. Its manual timestamp is operator-maintained. Python fails closed when the news call returns a warning, but feed success does not produce sentiment scoring; freshness/coverage/licensing are unverified. No rollover/weekend policy is present.
- **Observability is insufficient for reliable reconstruction and alert response.** Console/file logs exist, but rejection paths do not consistently log all required signal inputs, spread, equity, margin, and final broker state; no verified alert delivery exists for disconnection, loss thresholds, rejects, repeated losses, or kill-switch events. Queue logging silently drops records when full, and disk errors can terminate its worker. EA `Print` logs are not a durable structured audit trail.
- **Deployment documentation presents unsafe/inconsistent settings.** `PRODUCTION_DEPLOYMENT_GUIDE.md` examples enable live mode and bind to `0.0.0.0`, while `deploy/DEPLOYMENT.md` requires paper mode and loopback. Linux MT5 bridge suitability is conditional and untested. Choose one authoritative, fail-safe deployment procedure and remove contradictory live examples.

### High

- **Standalone root EA uses unfinished-candle indicators and omits its advertised H4 bias.** This is repainting/inconsistent with the preferred EA and Python behavior. The two EA source files must not be treated as equivalent release artifacts.
- **EA volume/price and stop validations need broker-specific proof.** Preferred EA clamps after step rounding, normalizes price only by digits, omits entry `OrderCheck` by default because async is enabled, and does not persist or retry failed trailing changes. Root EA's freeze check is not a valid freeze-distance check.
- **Hedging and netting semantics are not tested.** Ownership checks use symbol and magic, which is good, but position counts and order-to-position identity differ by account mode. Netting can merge manual/other-strategy exposure; no account-mode guard or scenario test exists.
- **There is no backtest harness or supplied performance evidence.** No regime-separated, out-of-sample, forward demo, parameter sensitivity, or Monte Carlo results. Spread/commission/swap/latency/slippage realism is not established. No PF, expectancy, Sharpe/Sortino, drawdown, recovery, win/loss, monthly stability, or trade-count evidence is supplied.
- **AI confidence and repeated-loss behavior have no explicit operating policy.** Schema validation and deterministic execution checks are positive; they do not replace confidence thresholding, provenance/prompt-injection handling, or a rule to stop/review after model-driven losses.
- **No emergency control is present in the EAs.** Python has API control states, but they are volatile and exposed by the shared browser token described above. No verified independent manual terminal/VPS stop procedure or remote kill test evidence was supplied.

## Failure And Recovery Matrix

No listed fault was injected against MT5, an EA, a broker, the VPS, or the live API. The “Actual/source behavior” column records what the code suggests; “Not run” is not a pass. “Close?” means whether existing positions are intentionally closed by the bot in that failure path.

| Failure scenario | Expected behavior | Actual/source behavior | New entries blocked? | Close existing positions? | Log / alert | Test status |
| --- | --- | --- | --- | --- | --- | --- |
| Internet disconnection | Fail closed, detect loss, no duplicate order on recovery | Python reconnects on operations; EA sends/rejects via terminal. Durable idempotency absent. | Usually, until connection restored | No automatic close | Some error logs; no verified alert | Not run |
| Broker-server disconnection | Block entries, preserve/reconcile managed positions after reconnect | Python retries initialize; EA readiness/order failures skip. | Yes when disconnected | No | Logs, alert unverified | Not run |
| Terminal restart | Reconcile positions/orders and restore all risk/control state before RUNNING | Python state/counters/control reset; EA daily baseline resets; position-state file only covers trailing risk | No, can resume RUNNING | No | Startup logs only | Not run |
| VPS restart | Restore reviewed version, settings, guards, and ownership safely | systemd restarts Python, but volatile state resets; EA restart state also resets | Not reliably | No | systemd logs | Not run |
| EA remove/reattach | No duplicate order; restore state | `g_lastBar`, pending id and daily baseline reset; next qualifying bar can issue entry | Not reliably | No | Initialization print | Not run |
| Duplicate `OnInit` / duplicate instance | Single-owner lease or hard block | No lock/lease in either EA; Python docs prohibit multiple processes but no enforcement | No | No | No duplicate-instance alert | Not run |
| Missing ticks / stale history | Reject stale data and retain management path | EAs are tick-driven; preferred EA skips if data unreadable, root checks Bars/CopyRates. Python health checks closed H1 freshness in API only; loop does not explicitly age-check H4. | Generally for missing indicator/tick | No; trailing also requires data/ticks | Some logs; no alert | Not run |
| Large spread | Reject entry above approved cap | Preferred EA checks spread; root EA does not; Python order path has no equivalent max-spread guard | Preferred EA yes; other paths no | No | Preferred EA silently returns; alert absent | Not run |
| Fast price gap | Reprice/revalidate stops and volume; block if risk invalid | Uses sampled quote, deviation and preflight vary by path; no gap circuit breaker or post-fill maximum-risk enforcement | Not guaranteed | No | Partial rejection/fill logs | Not run |
| Market open/close | Respect sessions; avoid unstable opening/closing window | Broker rejects or symbol quotes gate; no session/rollover policy | Broker-dependent | No | Generic retcode logs | Not run |
| Insufficient margin | Broker preflight rejects without duplicate; preserve safe exposure | Python calculates margin and calls `order_check`; EA relies mostly on server result (preferred async skips check) | Yes after reject | No | Logs; alert absent | Unit mocks only; broker test not run |
| Rejected order / requote | Record decision and retcode; retry only with idempotency | Python skips retry; EA sync retries transient retcodes; async one send. Root one send. | Per current attempt, yes | No | Logs, incomplete decision context | Not run |
| Partial fill | Reconcile filled and residual volumes, position and risk state | Python treats non-DONE as rejection; preferred EA logs DONE_PARTIAL as accepted but does not reconcile residual | No durable block on residual | No | Partial log only | Not run |
| Symbol specification change | Refresh metadata and recalculate tick/volume/stops before order | Python now expires cached specs after five minutes; EA reads live specs each call. No broker specification-change test. | Expected after TTL | No | May log broker rejection | Unit cache-expiry test passed; broker test not run |
| Balance/equity change | Recompute limits from approved baseline and latch loss limits | Per-trade size uses current equity; daily/peak state is volatile; no external balance-change reconciliation | Sometimes | No | Guard logs on threshold | Unit tests cover peak latch only in-process |
| Clock/timezone/DST difference | Use one authoritative broker/UTC policy and test boundary rollover | Python daily guard uses UTC date; EA uses server `TimeCurrent`; news timestamps cross sources and EA manual timestamp is server time | Ambiguous at boundaries | No | No clock-drift alert | Not run |
| AI/API timeout | HOLD, no order, back off/circuit-break | AI exception becomes HOLD; in-process circuit breaker opens after failures; no order on HOLD | Yes | No | Logs; alert absent | No dedicated timeout integration test supplied |
| Malformed AI response | Strictly reject to HOLD | Pydantic/schema validator does this | Yes | No | Error log, no alert | Unit test coverage not confirmed by this audit |
| Invalid/contradictory AI instruction | Deterministic validation rejects before broker send | Symbol/required stops and stop orientation checked; deterministic signal and execution risk checks block. No confidence threshold or bounded RR policy. | Usually | No | Proposal/block logs | Not run against malicious instructions |
| AI service unavailable | Deterministic fallback or safe stop | HOLD; current deterministic sentiment gate also blocks directional entries | Yes | No | Error log; alert absent | Not run against real outage |
| Repeated AI losses | Reduce/stop and require operator review | No model-loss counter or loss-triggered AI circuit breaker | No | No | No specific alert | Not run |
| Database failure | Fail closed and preserve audit trail | No database is used; runtime snapshots are memory-only | N/A | No | N/A | Not applicable |
| File/logging failure | Stop entries or switch to durable secondary sink and alert | Python queue drops silently at capacity; worker can die on file I/O error; state save failure only logs. EA relies on terminal logs. | No | No | Not reliably; alert absent | Not run |
| Network/news logging failure | Do not treat unverified calendar as safe; redact secrets | Python news warnings block in the strategy path; EA calendar can return no events and continue. NewsAPI exceptions may include request URL details. | Python yes on warning; EA not guaranteed | No | Error logs, alert absent | Unit test verifies warning only |
| Emergency stop / kill switch | Immediate entry block independent from frontend; explicit close policy; survives restart | Python control API blocks entries in process but resets on restart; no EA kill switch | In-process Python only | No | API/runtime logs, alert unverified | Unit state tests only |
| Hedging vs netting | Verify ticket, magic, volume and close/modify behavior on both modes | No broker account-mode-specific guard or tests | Not established | Management only by matching magic | Logs insufficient for acceptance | Not run |
| Limit/stop order handling | Validate pending orders, expiry, cancellation, idempotency | Neither EA nor Python strategy submits limit/stop entries; market deals only | N/A | N/A | N/A | Not implemented |

## Client Acceptance Checklist

“Actual result” is deliberately marked not executed where there is no matching integration evidence. Every row requires retained logs/reports/screenshots or broker-history evidence before promotion.

| Requirement | Test case | Expected result | Actual result / evidence | Pass/fail | Severity | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| Closed-candle strategy | Replay forming and closed bars in tester | Only completed trigger and bias bars affect decisions | Python source uses start position 1; preferred EA uses shifts 1/2. No tester evidence. | Fail: evidence absent | High | Add deterministic replay tests and EA tester proof |
| MTF synchronization | Delay H4 history and test bar boundary | Reject missing/stale/misaligned H4; no look-ahead | No explicit freshness/alignment test | Fail | High | Verify H4 timestamp/data age before signal |
| Invalid indicator data | Empty, NaN, delayed, insufficient data | Block signal/order without corrupting tracker | Python has guards; EA ReadValue guards copy count/number. Scenario not run. | Partial | High | Test all handles and recover same bar when data becomes ready |
| AI schema and hard gate | Malformed/extra fields/wrong symbol/invalid SL/TP/volume | HOLD or block; `order_send` never called | Schema and final risk checks exist; runtime negative tests incomplete | Partial | Critical | Add adversarial proposal tests at order boundary |
| Sentiment correctness | Feed success, neutral score, outage and stale event | Policy-defined fallback; actual data score meaningful | Current score always zero; directional gate cannot pass | Fail | Blocker | Implement validated sentiment scoring or remove/document requirement |
| Risk per trade | Minimum-lot boundary and loss-at-SL calculation per symbol | Never exceed approved monetary risk incl costs | Python raises to minimum lot; target can be exceeded | Fail | Critical | Reject when minimum lot exceeds approved risk; use broker loss calc |
| Aggregate open risk | 3 positions at stops, correlated symbols | Sum risk stays below client cap | Position count and heuristic correlation only; no aggregate SL-risk cap | Fail | Critical | Enforce aggregate risk at final order gate |
| Daily / weekly / peak loss | Cross thresholds then restart/UTC rollover | Latch persists as approved; entries blocked | Python process-local; no weekly guard; EA daily baseline volatile | Fail | Blocker | Persist state atomically and test restart/day/week boundaries |
| Daily trade / consecutive loss limits | Hit each cap and restart | No more entries until approved reset | Python trade count resets on process restart; no consecutive loss cap | Fail | Critical | Persist deal-based counters and add consecutive-loss latch |
| Spread / slippage | Inject high spread and adverse fill | Block beyond approved cap; reject/mitigate excessive fill | Spread cap only preferred EA; Python logs slippage after fill but does not enforce | Fail | Critical | Common pre-trade spread cap and explicit post-fill policy |
| Volume normalization | Min/max/step edge values | Valid step and no rounding above risk cap | Preferred EA floors then caps; Python min clamps upward | Fail | Critical | Normalize down; reject below min and cap to step-valid max |
| Price normalization | Tick size differs from decimal point | All requested prices lie on tick grid | Digits rounding only; no broker test | Fail | High | Normalize to tick size and validate with OrderCheck |
| Stops/freeze | Freeze and stop-level boundary by direction | Correct stop side/distance; invalid requests blocked | Root EA freeze comparison is unrelated to entry stop validity; no test | Fail | High | Correct directional checks and test symbol specifications |
| Broker reject/margin | Reject, no money, disabled, market closed, requote | No duplicates; complete retcode audit; safe skip | Python preflight; MT5 EA behavior not tested, async bypasses check | Partial | Critical | Test all retcodes and persist intent/order IDs before retry |
| Partial fill / async duplicate | Delay fill, partial fill, restart before callback | Reconcile full/residual position without second order | Python treats partial as rejection; EA async pending state volatile | Fail | Blocker | Durable idempotency, pending-order scan, partial fill reconciliation |
| Hedging and netting | Same symbol positions, manual trade, two bot tickets | Manage only explicitly owned exposure on both account modes | No account-mode-specific tests | Fail | Critical | Add account mode validation and broker acceptance tests |
| Position trailing | Restart after SL moves; compare original R | Trail from stable original risk; stop only improves | Python file exists but ticket/order identity not proven; EA has no persistent state | Fail | High | Reconcile positions by stable identifier and persist original risk |
| Restart/reconnect state | Kill terminal/service/VPS and reconnect | Stay halted until state/history reconciliation completes | In-memory risk/control resets; no chaos-test evidence | Fail | Blocker | Persist guard/control state; reconcile broker history before RUNNING |
| Manual/remote emergency stop | Invoke, restart, confirm entry block and policy for open positions | Independent stop survives process/network and records operator | Python endpoint only; browser token shared; EA has no kill switch | Fail | Blocker | Host/broker-level stop plus durable authenticated operator control |
| News / rollover / weekend | Calendar outage, stale event, Friday close, rollover | Explicit no-entry windows; position policy documented | EA calendar failure can fail open; no rollover/weekend policy | Fail | Critical | Use verified provider and session-aware blackout policy |
| Observability and alerts | Reconstruct a trade; force reject/drawdown/disconnect/log failure | Complete timestamped decision-to-fill trail; alert reaches operator | Partial logs; no tested alert route; bounded logs/queue drops | Fail | Critical | Structured durable audit ledger, alerts and monitoring drill |
| Credentials and production settings | Inspect bundle, test wrong account, inspect logs | No public secrets; separate demo/live; locked reviewed limits | Shared API token in public bundle; no account-mode gate; docs conflict | Fail | Blocker | Server-side auth/RBAC, environment separation, validated immutable profile |
| Backtest robustness | Multiple regimes, OOS, sensitivity, Monte Carlo | Full metrics and realistic execution assumptions | README says no backtest harness; no results supplied | Fail | High | Implement independent harness and publish reproducible reports |
| Demo forward test | Full market week per intended broker/symbol | Reconcile every fill, guard, restart, news event | None supplied | Fail | Blocker | Complete supervised demo acceptance period |
| Reproducible release | Build EA and Python artifact with version/config hash | Exact tested artifact can be rolled back and rebuilt | Revision `ce6da2d` identified; no EA compile artifact/build manifest/config approval | Fail | Critical | Version and hash final artifacts/config; retain build/test evidence |

## Failed Checks

Repository pytest result: **93 passed, 2 failed, 1 warning**.

- `tests/test_execution_guards.py::test_place_order_respects_runtime_control` fails because its fake MT5 namespace omits `orders_get`, now used by `execution.place_order`. This is a stale fixture and leaves the success path unverified by that test.
- `tests/test_strategy_gaps.py::TestGenerateSignal::test_neutral_drift_allows_both_directions` expects a neutral sentiment reading to allow BUY, while current strategy defaults require a sentiment feed and a directional score above/below configured thresholds. This is a test/product-policy mismatch requiring an explicit decision; do not change the safety gate just to satisfy the old assertion.
- Pytest also emitted a pandas-ta Copy-on-Write deprecation warning.
- No MQL5 compile/test, Strategy Tester, broker simulation, chaos test, demo forward test, or production deployment test was run. Wine is present, but MetaEditor is not.

## A. Executive Verdict

**NOT READY.** Do not enable live orders. The selected EA build is uncompiled/unverified; Python's current deterministic sentiment path blocks directional orders; daily/peak/control risk state is restart-volatile; several promised limits are absent or misdocumented; and there is no forward test, robust performance evidence, or verified emergency alert/shutdown drill. “Paper” mode suppresses Python `order_send`, but that does not validate EA trading or broker fills.

## B. Top Ten Risks

1. Preferred MQL5 release has no verified successful MetaEditor compile.
2. Python's built-in sentiment score is always zero, so its deterministic entry gate blocks BUY/SELL.
3. Restart resets Python daily loss, peak drawdown, trade-count and kill/control state.
4. Public frontend contains the shared API token, undermining remote control endpoint authentication.
5. No final, account-wide maximum open stop-loss risk is enforced.
6. Partial fills and async pending orders are not durably reconciled/idempotent.
7. Demo/live account selection is not programmatically verified; rollout examples conflict.
8. Original risk distance may not map reliably from Python order ticket to position ticket after restarts/netting.
9. Spread, slippage, week-loss, consecutive-loss, rollover/weekend and alert controls are absent or incomplete across execution paths.
10. No backtest/OOS/Monte Carlo/forward-test evidence supports the strategy or operational assumptions.

## C. Failed Tests

Initial baseline pytest had 93 passed and 2 failed. The execution failure was a stale fake MT5 object without `orders_get`; the strategy failure asserted that neutral/unavailable sentiment should permit a trade, contrary to the fail-closed default. The test double now includes `orders_get`, and the strategy regression asserts that unavailable sentiment blocks. Final full-suite result: **99 passed, 1 pandas-ta deprecation warning**. These unit tests are not evidence of broker execution or profitability. No broker-boundary, MQL5, or recovery test has passed because none was executed.

## D. Required Fixes Before Live Deployment

1. Select exactly one canonical execution path and compile/version the exact MQL5 artifact on the target MetaEditor build; resolve compiler diagnostics and retain build logs/hash.
2. Correct Python signal/news behavior: provide a real, timestamped, validated directional sentiment score or make technical-only policy explicit; add tests proving intended trades and fail-closed feed outages.
3. Implement durable risk and control state. On startup, reconcile broker positions/deals/orders before allowing entries; require operator re-arm after a prior halt.
4. Enforce approved aggregate open-risk limits at the final execution boundary; the Python minimum-lot oversizing path is now blocked, but still requires per-symbol broker validation.
5. Add account-mode/account-identity checks, idempotent order intents, order/position reconciliation, and correct partial-fill handling on netting and hedging demo accounts.
6. Normalize every price to tick size; use broker-supported filling policies and final order preflight; enforce spread and post-fill slippage policy.
7. Add and persist weekly loss, peak drawdown, trade-count, consecutive-loss and symbol/correlation caps; document close-vs-hold behavior for open positions after each trip.
8. Replace browser-shipped shared API token auth for remote deployments; provide least-privilege user/operator roles, TLS, private network controls, and demo/live credential segregation.
9. Make event/calendar outages and stale event data behavior explicit; add tested rollover, weekend, market-session and clock-boundary rules.
10. Add durable structured decision/order audit records and independent alerts; test disk-full, queue-full, network-down and alert delivery failures.
11. Correct deployment docs so risk values, API bind, MT5 runtime prerequisites, frontend auth, and paper/live modes agree with actual configuration code.
12. Pass all unit tests, add deterministic strategy/execution/recovery tests, run realistic multi-regime backtests and OOS/Monte Carlo analysis, then complete at least one full demo market-week for each intended broker/account mode.

## E. 30-Day Controlled Rollout Plan

| Period | Gate and work | Promotion criteria |
| --- | --- | --- |
| Days 1-3 | Freeze a canonical strategy and execution path; resolve compile failures; approve documented risk limits, symbols, account mode, broker and stop/close policy. | Exact sources/config versioned; MetaEditor compile is clean; no live credentials configured. |
| Days 4-7 | Implement durable guards, account identity, final aggregate risk, price/volume normalization, order idempotency/partial-fill reconciliation, private API auth and structured alerts. | Unit tests pass; focused fault tests prove every hard limit blocks `order_send`; restart restores HALTED state. |
| Days 8-12 | Run MT5 Strategy Tester with realistic spread, commissions, swaps, slippage, delays and all intended symbols; separate development/optimization from OOS periods. | Reproducible reports include requested performance/risk metrics and no look-ahead; parameter sensitivity and trade concentration reviewed. |
| Days 13-19 | Run supervised demo forward test, including market open/close, news windows, disconnect/reconnect, terminal/VPS restart, rejected and partial fills, and both hedging/netting if supported. | At least one full market-week per target configuration; broker history reconciles exactly; zero unresolved critical/high operational issues. |
| Days 20-23 | Run chaos/recovery and security drills; verify alerts, remote/manual shutdown, credential isolation, rollback and host permissions. | Independent operator can stop entries, apply approved position policy, restore service without losing guard state, and verify logs without secrets. |
| Days 24-27 | Continue demo at minimum risk; compare shadow decisions and actual broker outcomes; freeze all parameters and configuration. | No unexplained order, missing audit record, unexpected duplicate, guard bypass, or reconciliation discrepancy. |
| Days 28-30 | Client sign-off and release review; prepare rollback, capital cap and daily supervision roster. | Live remains disabled unless every blocker/critical is closed, all required evidence is attached, client limits signed, and final build/config hashes match the tested artifacts. If any gate fails, restart the demo qualification window. |

No automatic live promotion occurs at Day 30. A calendar milestone is not evidence of readiness.

## F. Evidence Still Missing

- Clean compile logs and `.ex5` hash for the selected EA; MetaEditor/terminal version and target broker symbol specifications.
- Broker/account environment and explicit client-approved risk limits, including aggregate risk and open-position liquidation policy.
- MT5 Strategy Tester configuration and reports across trending, ranging, volatile, low-volatility, news-driven and crisis markets; train/validation/OOS split and parameter stability.
- Profit factor, expectancy, Sharpe/Sortino, max drawdown, recovery factor, win rate, average win/loss, max consecutive losses, trade count, monthly stability, and concentration of returns.
- Realistic spread, commission, swap, slippage, latency and execution-delay assumptions/results.
- Monte Carlo trade-order randomization and spread/slippage/delay perturbation results.
- Full-market-week demo forward report, order/deal history, position reconciliation, and evidence for hedging/netting behavior.
- Executed fault-injection evidence for every row in the failure matrix, including terminal/VPS restart, partial fill, news/API outages, malformed AI, disk/log failure and account changes.
- Proof that emergency shutdown blocks new orders, management behavior is approved, alerts reach on-call staff, and HALTED state survives reboot/reconnect.
- Security evidence for API authorization, TLS, network ACLs, credential rotation, public frontend contents, secret-safe logs, and demo/live separation.
- Final signed configuration, release tag, source/build hashes, dependency lock/build reproducibility, rollback artifact, operator runbook and client acceptance sign-off.
