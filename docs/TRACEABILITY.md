# Traceability Matrix

> **Rules:** Status is ✅ only when **all three** evidence columns are filled in.
> The Demo evidence column must be filled manually (screenshot / Experts-log export / screen recording).
> Never let the AI tool mark its own work as done — you verify it yourself.

Status key: ✅ = all evidence present · ⬜ = evidence incomplete · 🔴 = not yet built

---

## How to fill this in

1. Run `scripts/audit.sh` — it fails on anything obviously wrong.
2. Run the test suite: `cd lib/ea-bridge && pytest -v` — paste the passing test IDs in the Test column.
3. For EA rows, run the live scenario on a demo account and save the Experts log export.
4. Only then change the status to ✅.

---

## Backend tasks

| Task | Description | Code location | Test that proves it | Demo evidence | Status |
|---|---|---|---|---|---|
| B-01 | Sign-up | [`app/routes/app.py:133`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L133-L157) | `test_integration_full.py::test_signup_returns_201_and_session_cookie` | — | ⬜ |
| B-02 | Sign-in + session cookie | [`app/routes/app.py:178`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L178-L196) | `test_integration_full.py::test_login_returns_401_bad_credentials` | — | ⬜ |
| B-03 | Email verify (`is_verified` field) | [`app/models.py:46`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L46) | `test_contracts.py::test_user_signup_validation` | — | ⬜ |
| B-04 | Password reset | Not implemented | — | — | 🔴 |
| B-05 | Google OAuth | Not implemented | — | — | 🔴 |
| B-06 | TOTP 2FA | [`app/models.py:50`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L50) (`two_factor_secret` field only) | No dedicated TOTP flow test | — | 🔴 |
| B-07 | Session revoke / logout | [`app/routes/app.py:203`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L203-L209) | `test_integration_full.py::test_logout_revokes_session` | — | ⬜ |
| B-08 | Pairing code created, 10 min TTL, single-use | [`app/routes/app.py:228`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L228-L233) · [`app/models.py:69`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L69-L83) · [`app/config.py:17`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/config.py#L17) | `test_integration_full.py::test_create_pairing_code_201` · `test_verification_int.py::test_INT_01_pair_valid_code` · `test_INT_02_pairing_code_single_use` · `test_INT_03_pairing_code_expired` | — | ⬜ |
| B-09 | Device pair endpoint | [`app/routes/ea.py:62`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/ea.py#L62-L149) | `test_integration_full.py::test_ea_pair_endpoint_returns_token_once` · `test_verification_int.py::test_INT_01_pair_valid_code` | — | ⬜ |
| B-10 | Device heartbeat + position sync | [`app/routes/ea.py:152`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/ea.py#L152-L256) | `test_integration.py::test_complete_ea_lifecycle` (step 3) · `test_INT_04` · `test_INT_05` · `test_INT_06` | — | ⬜ |
| B-11 | Device revoke | [`app/routes/app.py:328`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L328-L348) | `test_integration_full.py::test_revoke_device_204` · `test_verification_int.py::test_INT_07_revoked_device_heartbeat` | — | ⬜ |
| B-12 | Presence ONLINE / STALE / OFFLINE | [`app/routes/app.py:111`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L111-L127) (`_calculate_presence`) | `test_integration_full.py::test_list_devices_empty_200` (presence field present) | — | ⬜ |
| B-13 | Signal states enforced (DB constraint + state machine) | [`app/models.py:200`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L200-L230) · [`app/routes/ea.py:259`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/ea.py#L259-L324) | `test_integration.py::test_complete_ea_lifecycle` (DELIVERED transition) · `test_verification_int.py::test_INT_08_illegal_state_transition` | — | ⬜ |
| B-14 | Signal expiry worker | Query-time filter in [`app/routes/ea.py:272`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/ea.py#L272-L279) — no background worker yet | `test_verification_int.py::test_INT_09_expired_signal_not_returned` | — | ⬜ |
| B-15 | Risk profile saved + enforced | [`app/models.py:164`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L164-L194) · [`app/routes/app.py:558`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L558-L605) | `test_integration_full.py::test_update_risk_profile_200` · `test_verification_int.py::test_INT_12_risk_check_symbol_not_allowed` | — | ⬜ |
| B-16 | Kill switch on/off | [`app/routes/app.py:607`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L607-L637) · [`app/routes/ea.py:232`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/ea.py#L232-L234) | `test_integration_full.py::test_kill_switch_200` · `test_verification_int.py::test_INT_11_kill_switch_reflected_in_heartbeat` | — | ⬜ |
| B-17 | Analytics rollups | [`app/routes/app.py:822`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L822-L891) | `test_integration_full.py::test_journal_metrics_200_empty` · `test_journal_heatmap_200_empty` | — | ⬜ |
| B-18 | Audit log append-only | [`app/models.py:288`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/models.py#L288-L310) | No append-only constraint test — **needs dedicated test** | — | 🔴 |
| B-19 | WebSocket / SSE pushes 6 event types | [`app/routes/app.py:896`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/routes/app.py#L896-L920) · [`app/realtime.py`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/lib/ea-bridge/app/realtime.py) | `test_integration_full.py::test_events_stream_401_without_auth` (auth only; 6-event-type test missing) | — | 🔴 |

---

## EA tasks

| Task | Description | Code location | Test that proves it | Demo evidence | Status |
|---|---|---|---|---|---|
| E-01 | EA pairs from `InpPairingCode` | [`AegisQuantEA.mq5:187`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L187-L213) · [`mq5:250`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L250-L295) | `tests/ea-scenarios/run_scenario.py` (EA-02 scenario) | _Experts log + screenshot_ | ⬜ |
| E-02 | Credentials stored only in `MQL5/Files` | [`AegisQuantEA.mq5:215`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L215-L248) | `tests/ea-scenarios/run_scenario.py` (EA-03 scenario) | _Experts log — token must NOT appear_ | ⬜ |
| E-03 | Heartbeat + signal polling on separate timers | [`AegisQuantEA.mq5:343`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L343-L449) | `tests/ea-scenarios/run_scenario.py` (EA-04/EA-05) | _Experts log showing separate timer IDs_ | ⬜ |
| E-04 | Exponential backoff on failure | [`AegisQuantEA.mq5:337`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L337-L340) | `tests/ea-scenarios/run_scenario.py` (EA-05 — backend recovery) | _Experts log showing increasing retry intervals_ | ⬜ |
| E-05 | 12-step signal pipeline + reject codes | [`AegisQuantEA.mq5:451`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L451-L555) | `tests/ea-scenarios/run_scenario.py` (EA-06…EA-14) | _Experts log per scenario_ | ⬜ |
| E-06 | Signal ID in order comment; no duplicate after restart | [`AegisQuantEA.mq5:464`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L464) · [`mq5:557`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L557-L580) | `tests/ea-scenarios/run_scenario.py` (EA-10 — restart mid-execution) | _Order ticket comment screenshot_ | ⬜ |
| E-07 | Panel: connection status, AI Auto, last signal, KILL, update badge | [`AegisQuantEA.mq5:683`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/ea/AegisQuantEA.mq5#L683-L796) | `tests/ea-scenarios/run_scenario.py` (EA-16, EA-17) | _Screenshot of panel in each state_ | ⬜ |

---

## Web tasks

| Task | Description | Code location | Test that proves it | Demo evidence | Status |
|---|---|---|---|---|---|
| W-01 | Onboarding wizard (5 steps, live pairing over WebSocket) | [`artifacts/onyx-fx/src/pages/Onboarding.jsx`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/artifacts/onyx-fx/src/pages/Onboarding.jsx) | Manual + Playwright/Cypress (`tests/web/onboarding.cy.ts`) | _Screen recording of full onboarding flow_ | ⬜ |
| W-02 | Overview, Signals + drawer, Risk, Journal, Devices, Settings | [`artifacts/onyx-fx/src/pages/`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/artifacts/onyx-fx/src/pages/) | Manual + Cypress (`tests/web/*.cy.ts`) | _Screenshot of each page_ | ⬜ |
| W-03 | Loading, empty, error and offline states on every screen | [`artifacts/onyx-fx/src/components/SkeletonLoaders.jsx`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/artifacts/onyx-fx/src/components/SkeletonLoaders.jsx) · `useBotFeed.js` | Cypress intercept tests | _Screenshot of skeleton + error + offline banner_ | ⬜ |
| W-04 | Mobile layout; dark/light themes; ⌘K; keyboard shortcuts | [`artifacts/onyx-fx/src/lib/theme.js`](file:///home/abdalla-msema/Desktop/msema4/aegis_quant/artifacts/onyx-fx/src/lib/theme.js) · `use-mobile.tsx` | Cypress viewport + theme + keyboard tests | _Screenshots at 375 px, 768 px, 1280 px, 1920 px in both themes_ | ⬜ |

---

## Integration test map (INT-01 … INT-14)

| INT ID | Scenario | Test function | Passing? |
|---|---|---|---|
| INT-01 | Pair with a valid code | `test_INT_01_pair_valid_code` | PASSED ✅ |
| INT-02 | Reuse the same pairing code | `test_INT_02_pairing_code_single_use` | PASSED ✅ |
| INT-03 | Pair with an expired code | `test_INT_03_pairing_code_expired` | PASSED ✅ |
| INT-04 | Heartbeat with a bad signature | `test_INT_04_heartbeat_bad_signature` | PASSED ✅ |
| INT-05 | Replay an identical signed request | `test_INT_05_nonce_replay` | PASSED ✅ |
| INT-06 | Timestamp 31 s old | `test_INT_06_clock_skew` | PASSED ✅ |
| INT-07 | Heartbeat from a revoked device | `test_INT_07_revoked_device_heartbeat` | PASSED ✅ |
| INT-08 | Illegal transition EXECUTED → DELIVERED | `test_INT_08_illegal_state_transition` | PASSED ✅ |
| INT-09 | Signal past its expiry | `test_INT_09_expired_signal_not_returned` | PASSED ✅ |
| INT-10 | Duplicate trade report | `test_INT_10_duplicate_trade_report` | PASSED ✅ |
| INT-11 | Kill switch on | `test_INT_11_kill_switch_reflected_in_heartbeat` | PASSED ✅ |
| INT-12 | Risk check: symbol not allowed | `test_INT_12_risk_check_symbol_not_allowed` | PASSED ✅ |
| INT-13 | Rate limit exceeded | `test_INT_13_rate_limit` | PASSED ✅ |
| INT-14 | Two users — isolation | `test_INT_14_user_isolation` | PASSED ✅ |

Run:
```bash
cd lib/ea-bridge
pytest tests/test_verification_int.py -v 2>&1 | tee /tmp/int_results.txt
```
Then update the **Passing?** column from the output.

---

## Selected Python MT5 execution candidate

The current qualification candidate is `lib/trading-engine` on Windows beside
MT5, as recorded in [`PRE_DEPLOYMENT_RELEASE_PLAN.md`](PRE_DEPLOYMENT_RELEASE_PLAN.md).
Rows remain ⬜ until broker/demo evidence is attached; code and local tests alone
do not qualify execution.

| Task | Description | Code location | Test / local evidence | Demo evidence | Status |
|---|---|---|---|---|---|
| P-01 | Closed-candle H1/H4 technical proposal gate | `lib/trading-engine/strategy.py`, `main.py` | `tests/test_strategy.py`, `tests/test_strategy_gaps.py` | Target-broker terminal journal and data freshness record | ⬜ |
| P-02 | Durable signal idempotency before broker send; ambiguous/partial outcome pauses | `lib/trading-engine/execution.py`, `api.py` | `tests/test_execution_gaps.py::TestLotSize::test_execution_intent_is_durable_and_only_operator_reconciliation_resolves_it` | Restart/outcome ambiguity drill; broker history must match intent comment and volumes | ⬜ |
| P-03 | Operator reconciliation required before re-arm | `lib/trading-engine/api.py` | Authenticated route behavior; source-level only | Reconciliation and re-arm audit record from demo | ⬜ |
| P-04 | Cost-aware historical development/OOS screening report | `scripts/backtest_python_strategy.py` | CLI smoke run only; synthetic data is not performance evidence | Broker history, contract-cost inputs, report hash, separate MT5 Strategy Tester report | ⬜ |
| P-05 | Broker qualification, risk response, exact order/deal/position reconciliation | `lib/trading-engine/execution.py` | Local unit tests do not cover broker execution | Full supervised demo-week log and broker statement reconciliation | ⬜ |

---

## Known gaps (must be closed before launch)

| Gap | Impact | Ticket |
|---|---|---|
| B-04 Password reset — not implemented | Users cannot self-recover accounts | — |
| B-05 Google OAuth — not implemented | Onboarding friction | — |
| B-06 TOTP 2FA — field exists, no flow | 2FA badge in UI is non-functional | — |
| B-18 Audit log append-only constraint — no test | A bug could silently mutate audit rows | — |
| B-19 SSE 6-event-type test — missing | Only auth guard tested, not the 6 payload shapes | — |
| E-01…E-07 Demo evidence — all ⬜ | EA live scenarios not yet run against real MT5 | — |
| W-01…W-04 Demo evidence — all ⬜ | Web manual checks not yet completed | — |
