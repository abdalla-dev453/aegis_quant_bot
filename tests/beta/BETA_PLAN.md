# Beta Test Plan

## Testers
- 5–10 traders with demo accounts only
- Duration: 2 weeks

## Task List for Testers

1. **Pair your terminal**
   - Open MT5, attach AegisQuantEA
   - Create a pairing code in the web app
   - Enter the code in the EA panel
   - Target: under 5 minutes

2. **Set your risk profile**
   - Choose a risk preset (Conservative, Balanced, Active)
   - Confirm the values in Settings → Risk

3. **Receive 5 signals**
   - Wait for the rule-based provider to send signals
   - Verify the UI shows EXECUTED or REJECTED with reason

4. **Use the kill switch**
   - Open an open position
   - Trigger the kill switch from the web app
   - Verify the EA closes the position

5. **Revoke and re-pair**
   - Revoke the device in Settings → Devices
   - Verify the EA shows "Not paired"
   - Create a new pairing code and re-pair

## Exit Criteria
- [ ] 0 critical or high bugs reported
- [ ] Median pairing time under 5 minutes
- [ ] All 5 task list items completed by at least 80% of testers
- [ ] No hard-fail conditions from the verification plan

## Data to Collect
- Time to first successful pairing (seconds)
- Confusing moments (free text)
- Bugs (with screenshots and steps to reproduce)
- Browser/OS/MT5 version
