# Web E2E Tests (Cypress)

## Setup
```bash
cd artifacts/onyx-fx
npm install
npm run dev  # starts frontend
npx cypress open
```

## Tests to run

### Onboarding
1. Visit `/onboarding`
2. Step through all 5 steps
3. Complete pairing
4. Verify success card shows broker and account

### Dashboard
1. Visit `/`
2. Verify devices list loads
3. Verify stat cards show balance/equity
4. Verify equity curve chart renders

### Signals
1. Visit `/signals`
2. Verify signal list loads
3. Click a signal to open drawer
4. Verify signal detail shows timeline

### Risk
1. Visit `/risk`
2. Update risk profile
3. Verify changes persist after reload

### Devices
1. Visit `/devices`
2. Verify device list loads
3. Revoke a device
4. Verify device disappears or shows revoked

### Settings
1. Visit `/settings`
2. Toggle dark/light theme
3. Verify theme persists after reload

### Offline
1. Go offline (DevTools → Network → Offline)
2. Verify offline banner appears
3. Go back online
4. Verify app reconnects

### Keyboard
1. Complete onboarding using only keyboard
2. Trigger kill switch using keyboard shortcut
