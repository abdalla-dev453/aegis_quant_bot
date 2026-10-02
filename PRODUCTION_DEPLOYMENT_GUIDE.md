# Production Deployment Guide for Aegis Quant Trading Bot

> **Legacy reference, not deployment authorization.** The current release status is **NO-GO for funded/live trading**. Follow [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md) for the paper-first deployment procedure and [PRODUCTION_RELEASE_CHECKLIST.md](PRODUCTION_RELEASE_CHECKLIST.md) for qualification gates. Values in this older document are not account-owner approvals; do not use its previous live-mode recommendation.

## Client-Server Compatibility Analysis ✅

### API Contract Verification
**Status: FULLY COMPATIBLE**

The existing API contracts between client and server remain intact:
- All existing endpoints (`/api/account`, `/api/risk`, `/api/positions`, etc.) are unchanged
- Client-side data structures in `botFeed.js` match server-side models in `models.py`
- New features are additive via new endpoints, not breaking changes
- Backward compatibility maintained for existing functionality

### New API Endpoints Added
- `/api/advanced-analysis` - Status of advanced technical analysis features
- `/api/self-healing` - Self-healing system status
- `/api/adaptive-optimization` - Adaptive optimization status
- `/api/adaptive-optimization/run` - Manual optimization trigger
- `/api/portfolio-risk` - Portfolio risk analysis
- `/api/system-health` - Comprehensive system health check

### Client-Side Updates
Added corresponding API client functions in `botFeed.js`:
- `fetchAdvancedAnalysisStatus()`
- `fetchSelfHealingStatus()`
- `fetchAdaptiveOptimizationStatus()`
- `runAdaptiveOptimization()`
- `fetchPortfolioRiskStatus()`
- `fetchSystemHealth()`

## Performance Optimization Analysis

### Current Performance Characteristics

**Bottleneck Analysis:**
1. **MT5 IPC Calls**: The main performance bottleneck is MT5 terminal communication
2. **AI API Calls**: OpenAI API calls have network latency (~500ms-2s)
3. **Indicator Calculations**: pandas_ta calculations are CPU-intensive
4. **Data Processing**: DataFrame operations for each symbol

**Optimizations Implemented:**
1. **Async Operations**: All heavy computations run in thread pools
2. **Concurrent Data Fetching**: H1 and H4 data fetched simultaneously
3. **Connection Pooling**: Symbol info caching to reduce MT5 calls
4. **Bounded Memory**: History queues limited to prevent memory bloat
5. **Non-blocking Logging**: Queue-based async logging system

### Performance Impact of New Features

**Additional Overhead:**
- **Advanced Indicators**: +50-100ms per symbol (ADX, MACD calculations)
- **Pattern Recognition**: +100-200ms per symbol (pattern detection algorithms)
- **Portfolio Risk Analysis**: +200-300ms (correlation calculations)
- **Self-Healing Monitoring**: +5-10ms (lightweight health checks)
- **Adaptive Optimization**: +50-100ms (performance analysis)

**Total Estimated Overhead:** ~400-600ms per trading cycle

**Mitigation Strategies:**
1. **Feature Flags**: All advanced features are opt-in via configuration
2. **Selective Activation**: Enable only high-impact features
3. **Async Processing**: Heavy operations don't block main trading loop
4. **Caching**: Results cached where appropriate
5. **Graceful Degradation**: System continues if features fail

### Production Performance Recommendations

**Minimum Hardware Requirements:**
- **CPU**: 2+ cores (4+ recommended for multiple symbols)
- **RAM**: 4GB minimum (8GB recommended)
- **Storage**: 20GB SSD
- **Network**: Stable internet connection (<100ms latency to broker)

**Optimization Configuration:**
```python
# config.py optimizations
STRATEGY.loop_poll_seconds = 10  # Reduce from 15 for faster reaction
ADVANCED_ANALYSIS.use_adx = True  # Low overhead
ADVANCED_ANALYSIS.use_macd = True  # Low overhead
PREDICTION.enable_pattern_detection = True  # Medium overhead
PREDICTION.enable_price_prediction = False  # High overhead (optional)
SELF_HEALING.enable_self_healing = True  # Very low overhead
ADAPTIVE.enable_adaptive_parameters = True  # Low overhead
ADVANCED_RISK.enable_portfolio_risk = True  # Medium overhead
```

## Production Deployment Configuration

### Docker Deployment (Recommended)

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ .

# Create models directory for ML models
RUN mkdir -p models

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Run the application
CMD ["python", "main.py"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  trading-bot:
    build: .
    container_name: aegis-quant-bot
    restart: unless-stopped
    environment:
      - TRADING_MODE=paper
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - API_TOKEN=${API_TOKEN}
      - API_HOST=127.0.0.1
      - API_PORT=8000
    volumes:
      - ./server/.env:/app/.env
      - ./models:/app/models
      - ./logs:/app/logs
    ports:
      - "127.0.0.1:8000:8000"
    network_mode: host  # Required for MT5 terminal access
    # Alternative: Use mt5linux bridge for containerized MT5 access
```

### Systemd Service (Linux)

**File: /etc/systemd/system/aegis-quant.service**
```ini
[Unit]
Description=Aegis Quant Trading Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=trading
WorkingDirectory=/home/trading/aegis_quant/server
Environment="PATH=/home/trading/aegis_quant/.venv/bin"
EnvironmentFile=/home/trading/aegis_quant/server/.env
ExecStart=/home/trading/aegis_quant/.venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aegis-quant

[Install]
WantedBy=multi-user.target
```

**Enable service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable aegis-quant
sudo systemctl start aegis-quant
sudo systemctl status aegis-quant
```

### Windows Service

**Use NSSM (Non-Sucking Service Manager):**
```bash
# Download NSSM from https://nssm.cc/download
nssm install AegisQuant "C:\Python311\python.exe" "C:\path\to\server\main.py"
nssm set AegisQuant AppDirectory "C:\path\to\aegis_quant"
nssm set AegisQuant AppEnvironmentExtra "PYTHONUNBUFFERED=1"
nssm set AegisQuant AppStdout "C:\path\to\logs\service.log"
nssm set AegisQuant AppStderr "C:\path\to\logs\service_error.log"
nssm set AegisQuant AppStopMethodSkip 6
nssm set AegisQuant AppRestartDelay 60000
nssm start AegisQuant
```

## Environment Configuration

### Production .env Template
```bash
# Core Configuration
TRADING_MODE=paper
API_HOST=127.0.0.1
API_PORT=8000
API_TOKEN=your_secure_token_here
CORS_ORIGINS=http://localhost:5173,http://your-dashboard-domain

# MT5 Credentials (SECURE THESE!)
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_secure_password
MT5_SERVER=your_broker_server
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

# AI Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o
OPENAI_TIMEOUT_SECONDS=30

# News API (Optional)
NEWS_API_KEY=your_news_api_key
YAHOO_FINANCE_RSS_URL=https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD%3DX%2CGBPUSD%3DX%2CGC%3DF&region=US&lang=en-US

# Advanced Features (PRODUCTION SETTINGS)
ADVANCED_ANALYSIS_USE_ADX=true
ADVANCED_ANALYSIS_USE_MACD=true
ADVANCED_ANALYSIS_ENABLE_REGIME_DETECTION=true
ADVANCED_ANALYSIS_USE_VOLUME_CONFIRMATION=true
ADVANCED_ANALYSIS_ENABLE_LEVEL_DETECTION=true

PREDICTION_ENABLE_PRICE_PREDICTION=false  # Disable ML for production initially
PREDICTION_ENABLE_PATTERN_DETECTION=true
PREDICTION_ENABLE_VOLATILITY_FORECASTING=true
PREDICTION_ENABLE_ENSEMBLE_AI=false

SELF_HEALING_ENABLE_SELF_HEALING=true
SELF_HEALING_ENABLE_DATA_QUALITY_CHECKS=true
SELF_HEALING_MAX_RECOVERY_ATTEMPTS=3

ADAPTIVE_ENABLE_ADAPTIVE_PARAMETERS=true
ADAPTIVE_OPTIMIZATION_WINDOW_DAYS=7
ADAPTIVE_MIN_TRADES_FOR_OPTIMIZATION=10

ADVANCED_RISK_ENABLE_PORTFOLIO_RISK=true
ADVANCED_RISK_ENABLE_VOLATILITY_ADJUSTED_SIZING=true
ADVANCED_RISK_MAX_PORTFOLIO_EXPOSURE_PCT=10.0
ADVANCED_RISK_MAX_CORRELATION_EXPOSURE_PCT=5.0
ADVANCED_RISK_MAX_CURRENCY_CONCENTRATION_PCT=7.0

# Python risk setting names (source defaults shown here are not approved limits)
RISK_PER_TRADE_PCT=1.5
MAX_DAILY_LOSS_PCT=4.0
MAX_DRAWDOWN_FROM_PEAK_PCT=8.0
MAX_TRADES_PER_DAY=6
MAX_CONCURRENT_POSITIONS=3

# Logging
LOG_FILE=trading_bot.log
LOG_LEVEL=INFO
```

## Deployment Checklist

### Pre-Deployment
- [ ] Test all features in paper trading mode
- [ ] Verify MT5 connection stability
- [ ] Test API key validity (OpenAI, News API)
- [ ] Validate configuration parameters
- [ ] Test client-server communication
- [ ] Verify self-healing functionality
- [ ] Test adaptive optimization logic
- [ ] Validate portfolio risk calculations

### Security Hardening
- [ ] Use strong API tokens
- [ ] Secure MT5 credentials
- [ ] Enable HTTPS for dashboard (if remote access)
- [ ] Implement rate limiting
- [ ] Regular security updates
- [ ] Monitor for unauthorized access
- [ ] Use firewall rules to restrict API access

### Monitoring Setup
- [ ] Configure log rotation
- [ ] Set up error alerting
- [ ] Monitor system resources (CPU, RAM, disk)
- [ ] Track API response times
- [ ] Monitor MT5 connection health
- [ ] Set up dashboard alerts
- [ ] Configure Prometheus metrics scraping

### Performance Monitoring
- [ ] Track trading cycle duration
- [ ] Monitor API latency
- [ ] Watch memory usage trends
- [ ] Check for memory leaks
- [ ] Monitor thread pool performance
- [ ] Track database/file I/O performance

## Production Rollout Strategy

### Phase 1: Baseline (Week 1)
1. Deploy existing system without new features
2. Establish performance baselines
3. Monitor stability and resource usage
4. Fine-tune basic risk parameters

### Phase 2: Advanced Analysis (Week 2)
1. Enable ADX and MACD indicators
2. Enable market regime detection
3. Enable support/resistance level detection
4. Monitor performance impact
5. Validate improved signal quality

### Phase 3: Risk Enhancements (Week 3)
1. Enable portfolio risk management
2. Enable volatility-based sizing
3. Enable self-healing system
4. Monitor recovery effectiveness
5. Validate risk reduction

### Phase 4: Intelligence Features (Week 4)
1. Enable pattern recognition
2. Enable volatility forecasting
3. Enable adaptive optimization
4. Monitor parameter adjustments
5. Validate performance improvements

### Phase 5: Optional ML (Week 5+)
1. Install scikit-learn and numpy
2. Train ML model on historical data
3. Enable price prediction
4. Monitor prediction accuracy
5. Validate ML contribution to performance

## Production Survival Assessment

### Reliability Features ✅
1. **Self-Healing**: Automatic recovery from common failures
2. **Graceful Degradation**: System continues when components fail
3. **Circuit Breakers**: Risk limits prevent catastrophic losses
4. **Data Validation**: Quality checks prevent bad trades
5. **Connection Resilience**: Automatic reconnection with backoff

### Performance Features ✅
1. **Async Processing**: Non-blocking operations
2. **Connection Pooling**: Reduced MT5 IPC overhead
3. **Bounded Resources**: Memory and CPU limits
4. **Efficient Caching**: Symbol info and calculation caching
5. **Optimized Logging**: Non-blocking async logging

### Risk Management ✅
1. **Multi-layer Risk**: Per-trade, daily, portfolio-level
2. **Correlation Awareness**: Prevents correlated exposure
3. **Concentration Limits**: Currency diversification
4. **Dynamic Sizing**: Volatility-adjusted positions
5. **Exit Strategies**: Intelligent position management

### Monitoring Features ✅
1. **Health Dashboard**: Comprehensive system status
2. **Performance Metrics**: Trading performance tracking
3. **Error Tracking**: Recovery attempt monitoring
4. **Resource Monitoring**: CPU, memory, disk usage
5. **API Metrics**: Response time and error rates

## Expected Production Performance

### Trading Cycle Performance
- **Baseline System**: ~2-3 seconds per cycle (3 symbols)
- **With All Features**: ~3-4 seconds per cycle (3 symbols)
- **Impact**: ~50% increase in cycle time
- **Acceptable**: YES (cycle time still < H1 bar duration)

### Resource Usage
- **Memory**: ~200-400MB baseline, +100-200MB with all features
- **CPU**: ~5-10% baseline, +10-15% with all features
- **Disk**: ~100MB/day for logs
- **Network**: ~1-2MB/day for API calls

### Scalability
- **Single Symbol**: Excellent performance
- **3 Symbols**: Good performance (current configuration)
- **5+ Symbols**: May need horizontal scaling
- **Recommendation**: Max 3-5 symbols per instance

### Reliability
- **Uptime Target**: 99%+ (excluding maintenance)
- **Recovery Time**: <1 minute for common failures
- **Data Loss Risk**: Minimal (state persistence)
- **MT5 Dependency**: Single point of failure (mitigated by self-healing)

## Conclusion

### Production Readiness: NOT APPROVED

Do not treat this legacy feature overview as evidence of production readiness. The current release is **not approved** for funded/live trading. The source audit identifies unresolved account-identity, durable risk-state, aggregate-risk, order reconciliation, security, broker-validation, and forward-demo gates. See [PRODUCTION_RELEASE_CHECKLIST.md](PRODUCTION_RELEASE_CHECKLIST.md) for current status and required evidence.

**High Confidence:**
- Core trading logic (proven in existing system)
- Risk management (multi-layer protection)
- Self-healing (automatic recovery)
- API compatibility (maintained)

**Medium Confidence:**
- Advanced indicators (well-tested algorithms)
- Portfolio risk (sound mathematical basis)
- Performance (acceptable overhead)

**Requires Testing:**
- ML prediction (needs training and validation)
- Ensemble AI (requires additional API keys)
- Complex pattern recognition (needs market validation)

### Deployment Recommendation

**Immediate Deployment (Week 1):**
- Enable: ADX, MACD, regime detection, self-healing
- Disable: ML prediction, ensemble AI
- Monitor: Performance, stability, recovery effectiveness

**Gradual Rollout (Weeks 2-4):**
- Add: Pattern recognition, volatility forecasting
- Add: Portfolio risk management
- Add: Adaptive optimization
- Monitor: Feature effectiveness, performance impact

**Advanced Features (Week 5+):**
- Consider: ML prediction (after training)
- Consider: Ensemble AI (if additional budget)
- Monitor: Prediction accuracy, cost/benefit

No production reliability or performance claim is established by this legacy document. Complete the current release checklist and retain test evidence before any promotion.