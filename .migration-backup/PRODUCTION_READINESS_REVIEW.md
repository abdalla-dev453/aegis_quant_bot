# AI Bot Production Readiness Review

## Executive Summary

The Onyx FX algorithmic trading system has a solid architectural foundation but requires several critical improvements before production deployment. This review identifies bottlenecks, reliability concerns, and optimization opportunities.

---

## Critical Issues (Must Fix Before Production)

### 1. **AI Engine - Single Point of Failure**
**File:** `server/ai_engine.py:82-136`

**Problem:** The `propose_trade()` function creates a new `AsyncOpenAI` client on every call. This creates connection overhead and no connection pooling.

**Impact:** ~200-500ms latency per AI call due to new TLS handshake.

**Fix:**
```python
# Module-level singleton
_client = None

async def get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=AI.api_key,
            timeout=AI.timeout_seconds,
            max_retries=2,
        )
    return _client

async def propose_trade(...):
    client = await get_client()
    ...
```

### 2. **No Circuit Breaker for OpenAI API**
**File:** `server/ai_engine.py:128-136`

**Problem:** Failures fall back to HOLD but there's no circuit breaker to stop hammering a failing API.

**Impact:** During OpenAI outages, the bot will spam failed requests every 15 seconds.

**Fix:** Add circuit breaker pattern:
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def _call_openai(...):
    ...
```

### 3. **MT5 Connection - Health Endpoint Readiness**
**File:** `server/api.py:157-205`

**Problem:** `/api/health` only returned connection state and always used HTTP 200, so a load balancer could route traffic to a disconnected or stale MT5 service.

**Resolved:** The endpoint now checks terminal connectivity, closed-candle freshness, and returns HTTP 503 when readiness fails. A separate unauthenticated `/healthz` endpoint provides process liveness for systemd and load balancers.

### 4. **Data Provider - Blocking Calls in Async Context**
**File:** `server/data_provider.py:324-390`

**Problem:** `get_rates()` is decorated with `@mt5_serialized` (thread lock) but called via `asyncio.to_thread()`. This is correct, but the lock is held for the entire IPC call + DataFrame construction.

**Impact:** Serializes all data fetching across symbols. With 3 symbols × 2 timeframes = 6 sequential MT5 calls per cycle.

**Fix:** Use connection pooling or batch requests where possible. Consider:
```python
# Fetch all symbols in one thread call
async def get_multi_rates(symbols, timeframe, n_bars):
    return await asyncio.to_thread(_fetch_multi_rates, symbols, timeframe, n_bars)
```

### 5. **No Graceful Degradation for News Feed**
**File:** `server/strategy.py:211-229`

**Problem:** `analyze_market_sentiment()` calls `get_latest_high_impact_news()` which can block for 10+ seconds on network timeouts.

**Impact:** Blocks the entire trading loop cycle.

**Fix:** Make news fetching fully async with timeout:
```python
async def analyze_market_sentiment(symbol: str) -> SentimentReading:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(get_latest_high_impact_news, 10, 24),
            timeout=5.0
        )
        ...
    except asyncio.TimeoutError:
        return _neutral_reading()
```

---

## High-Priority Optimizations

### 6. **Pandas-TA Performance**
**File:** `server/strategy.py:67-70`

**Problem:** `pandas_ta` is convenient but slow. Each indicator call creates intermediate Series.

**Optimization:** Pre-compute with vectorized operations or use `ta-lib` (C bindings):
```python
# Current: ~15ms per symbol per timeframe
# With ta-lib: ~2ms per symbol per timeframe
import talib
out["ema_50"] = talib.EMA(out["close"].values, timeperiod=50)
```

### 7. **Symbol Info Cache Invalidation**
**File:** `server/execution.py:92-142`

**Problem:** `_symbol_cache` has no TTL and only invalidates on explicit call. Broker changes (margin, contract specs) won't be reflected.

**Fix:** Add TTL-based invalidation:
```python
_symbol_cache: Dict[str, tuple[_SymbolData, float]] = {}  # (data, timestamp)
_CACHE_TTL = 300  # 5 minutes

def _get_symbol(symbol: str) -> _SymbolData:
    now = time.time()
    with _cache_lock:
        if symbol in _symbol_cache:
            data, ts = _symbol_cache[symbol]
            if now - ts < _CACHE_TTL:
                return data
    # ... fetch and cache with timestamp
```

### 8. **Error Logging - Sensitive Data Exposure**
**File:** `server/ai_engine.py:130-132`

**Problem:** Raw AI response logged to error log on validation failure. Could contain market data or prompts.

**Fix:** Sanitize before logging:
```python
_error_logger.error(
    "Invalid AI response for %s: %s | raw_len=%d",
    symbol, exc, len(raw_response)
)
```

### 9. **Position State Persistence - Race Condition**
**File:** `server/execution.py:157-179`

**Problem:** `_save_position_state()` writes to temp file then renames. On Windows, rename can fail if file is open elsewhere.

**Fix:** Use proper file locking or SQLite:
```python
import sqlite3
# Use SQLite with WAL mode for concurrent access
```

---

## Medium-Priority Improvements

### 10. **Trading Loop - No Dead Man's Switch**
**File:** `server/main.py:220-264`

**Problem:** If the event loop blocks (GC pause, CPU starvation), the bot stops processing candles but positions remain open.

**Fix:** Add watchdog thread:
```python
import threading
_last_heartbeat = time.time()

def heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()

# Watchdog thread
def watchdog():
    while True:
        time.sleep(10)
        if time.time() - _last_heartbeat > 30:
            logger.critical("Main loop stalled! Initiating emergency halt.")
            # Trigger emergency halt
```

### 11. **Rate Limiting on API - No Per-User Quotas**
**File:** `server/api.py:49-62`

**Problem:** Rate limiting is per-IP only. No per-user or per-endpoint quotas.

**Fix:** Add token-bucket per API key:
```python
_rate_buckets: dict[str, TokenBucket] = {}

def rate_limit(request: Request, bucket: str, limit: int, window: int = 60):
    api_key = request.headers.get("X-API-Key", "anonymous")
    bucket_key = f"{api_key}:{bucket}"
    ...
```

### 12. **Configuration - No Hot Reload**
**File:** `server/config.py`

**Problem:** Config changes require restart. Risk parameters should be adjustable at runtime.

**Fix:** Add `/api/settings/risk` POST endpoint with validation.

---

## Low-Priority / Nice to Have

### 13. **Metrics / Observability**
- Prometheus `/metrics` endpoint and request/latency gauges are present.
- Track: orders placed, latency percentiles, AI API latency, MT5 IPC latency
- Add structured logging (JSON) for log aggregation

### 14. **Test Coverage**
- Unit tests for `compute_indicators`, `generate_signal`, `calculate_lot_size`
- Integration tests with mock MT5
- Chaos testing: network partition, MT5 restart, API timeout

### 15. **Deployment Hardening**
- systemd service with `Restart=on-failure`, `WatchdogSec=120`, non-root user, and restricted filesystem paths
- SELinux/AppArmor profile
- Separate data directory with restricted permissions

---

## High-Speed Execution Optimization Plan

For sub-second order execution (critical for scalping/HFT-style strategies):

| Component | Current | Target | Action |
|-----------|---------|--------|--------|
| MT5 IPC latency | ~5-15ms | <5ms | Keep terminal local, disable Windows Defender on MT5 dir |
| Data fetch (H1+H4) | ~50-100ms | <20ms | Batch symbols, use `copy_rates_from_pos` once per symbol |
| Indicator calc | ~15ms | <3ms | Switch to `talib` (C bindings) |
| AI proposal | ~2-5s | <500ms | Cache client, reduce context, use GPT-4o-mini for speed |
| Order validation | ~10-20ms | <5ms | Cache symbol info, pre-validate |
| Order send | ~50-200ms | <100ms | Use `ORDER_FILLING_FOK`, reduce deviation |

### Recommended Architecture for High-Speed:
```
┌─────────────────────────────────────────────────────────────┐
│                    Trading Loop (async)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Data Fetch  │  │  Signals    │  │  Execution          │  │
│  │ (parallel)  │─▶│ (vectorized)│─▶│  (serialized,       │  │
│  │ per symbol  │  │  per symbol │  │   prioritized)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Code Changes for Speed:

1. **Parallelize data fetching across symbols:**
```python
# In trading_loop:
tasks = [evaluate_symbol(sym, tracker) for sym in symbols]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

2. **Use `talib` instead of `pandas_ta`:**
```python
# strategy.py
import talib
out["ema_50"] = talib.EMA(out["close"].values, 50)
out["ema_200"] = talib.EMA(out["close"].values, 200)
out["rsi"] = talib.RSI(out["close"].values, 14)
out["atr"] = talib.ATR(out["high"].values, out["low"].values, out["close"].values, 14)
```

3. **Cache AI client and reduce prompt size:**
```python
# ai_engine.py - strip non-essential context for speed
```

4. **Pre-warm MT5 connection and symbol selection at startup:**
```python
# main.py - move resolve_and_validate_symbols before loop
```

---

## Deployment Checklist

- [ ] Fix all Critical Issues (#1-5)
- [ ] Implement High-Priority Optimizations (#6-9)
- [x] Add health endpoint with MT5 terminal and candle-freshness checks
- [x] Add Prometheus metrics endpoint
- [x] Configure systemd service with watchdog and non-root hardening
- [ ] Run load test: 1000 orders simulated, verify <100ms p99
- [ ] Chaos test: kill MT5 terminal, verify auto-reconnect
- [ ] Chaos test: block OpenAI API, verify circuit breaker
- [ ] Verify no sensitive data in logs
- [ ] Document runbook for common failures

---

## Conclusion

The bot is **architecturally sound** for a research/alpha deployment but **not production-ready** for live capital without addressing the Critical Issues. The async architecture with thread-pool MT5 calls is correct for Python's GIL limitations. With the fixes above, the system can achieve reliable sub-second order execution suitable for systematic swing/day trading strategies.