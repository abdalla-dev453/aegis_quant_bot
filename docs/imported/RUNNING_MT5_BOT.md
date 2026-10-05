# Aegis Quant MT5 Bot: Runbook

Aegis Quant contains a Python trading bot, two MetaTrader 5 Expert Advisor scaffolds, and a React monitoring dashboard. The bot is intended for controlled demo or paper testing first. It is not a guarantee of profit and must not be treated as unattended financial advice.

## Choose an execution mode

### Python bot

Use the Python bot when you want the repository's headless trading loop:

- H4 EMA trend bias and H1 EMA trigger
- RSI momentum confirmation
- sentiment confirmation
- high-impact news blackout from the configured sentiment provider
- ATR-based stop-loss/take-profit and broker-aware position sizing
- trailing-stop management

The Python bot requires a Windows machine with the MetaTrader 5 desktop terminal installed and logged into the target broker account. The `MetaTrader5` Python package communicates with the local terminal; it does not connect directly to a broker from Linux or from a browser.

### MT5 Expert Advisor

Use an EA when you want execution inside MetaTrader 5 through MetaEditor. The source files are:

- `AegisQuantEA.mq5`
- `mt5/AegisConfluenceEA.mq5`

`mt5/AegisConfluenceEA.mq5` is the preferred scaffold for the multi-timeframe confluence flow. `AegisQuantEA.mq5` is a smaller root-level scaffold and should be compiled and tested separately before use.

Do not run the Python bot and an EA against the same account and symbol at the same time unless you deliberately configure separate magic numbers and understand the resulting position-management interactions.

## Python bot setup

1. Install MetaTrader 5 on Windows.
2. Open the terminal and log into a demo account manually.
3. Confirm the broker's exact symbol names. They may include suffixes such as `.a`, `.pro`, or `-ECN`.
4. Create a Python environment and install the server requirements:

   ```powershell
   cd server
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

5. Set credentials in the Windows shell. Never commit them to the repository:

   ```powershell
   $env:MT5_LOGIN = "12345678"
   $env:MT5_PASSWORD = "your-password"
   $env:MT5_SERVER = "YourBroker-Demo"
   $env:MT5_TERMINAL_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"
   $env:API_TOKEN = "generate-a-long-random-token"
   ```

6. Configure symbols and risk in `server/config.py`, or adapt the configuration to load all operational values from environment variables or a secrets manager.
7. Start the bot:

   ```powershell
   python main.py
   ```

8. Watch the console and `trading_bot.log`. Stop it with `Ctrl+C`.

The server API requires the `X-API-Key` header on every route. Start the
dashboard with the same token in a second terminal:

```powershell
cd client
npm install
$env:VITE_API_BASE = "http://127.0.0.1:8000"
$env:VITE_API_TOKEN = $env:API_TOKEN
npm run dev -- --host 127.0.0.1
```

Use HTTPS or a private network before using live credentials. Never commit
`API_TOKEN`, `VITE_API_TOKEN`, or MT5 credentials.

If the terminal, login, credentials, or symbols are unavailable, the bot should stop or skip the affected operation rather than place an order.

## MT5 EA setup

1. On Windows, open MetaTrader 5.
2. Open **File > Open Data Folder**, then place the selected `.mq5` file in `MQL5\Experts`.
3. Open the file in MetaEditor and compile it with **F7**.
4. Resolve any broker-specific compile or symbol issues before attaching it to a chart.
5. Attach the EA to the intended symbol and enable **Algo Trading**.
6. Begin on a demo account with the lowest practical risk.
7. Review the **Experts** and **Journal** tabs for initialization, stop validation, margin, and trade-server retcodes.

The preferred confluence EA has these main inputs:

- `InpSymbol`: symbol; blank means the chart symbol
- `InpTriggerTF`: normally H1
- `InpBiasTF`: normally H4
- `InpFastEma` / `InpSlowEma`: default 50 / 200
- `InpRsiPeriod`: default 14
- `InpRiskPerTradePct`: default 1.5% of equity
- `InpAtrStopMult` / `InpAtrTpMult`: default 1.5 / 3.0
- `InpMaxConcurrentPositions`
- `InpAllowBuy` / `InpAllowSell`
- `InpUseNewsBlackout`
- `InpNewsBlackoutMinutes`
- `InpNextNewsTimestamp`

`InpNextNewsTimestamp` is a manually supplied server-time event timestamp. It is not an automatic economic-calendar integration. Set it to `0` only when no configured event is pending and the event risk has been assessed independently.

## How the strategy works

A new decision is made on a newly closed trigger-timeframe candle, not on an unfinished candle. A long entry requires, in substance:

- H4 fast EMA above H4 slow EMA
- H1 fast EMA above H1 slow EMA
- H1 RSI at or above the bullish neutral threshold and below overbought
- configured sentiment confirmation in the Python path
- no active high-impact news blackout
- valid broker prices, stops, freeze-level conditions, volume, and margin

A short entry uses the inverse conditions. The Python implementation also requires RSI to be moving in the direction of the trade. The EA scaffold uses the explicit RSI directional bands and should be validated in MetaEditor and Strategy Tester before relying on it.

Stops and targets are derived from ATR, then checked against broker stop levels. The execution layer uses symbol tick size/value and volume steps rather than assuming that every instrument has the same pip economics.

## What a trader can do

A trader can:

- run the bot on a demo account for forward testing
- choose supported broker symbols and timeframes
- change risk percentage, ATR multipliers, position caps, slippage, and direction permissions
- disable buys or sells independently
- monitor open positions, logs, equity, and signals through MT5 or the dashboard
- stop the Python process or disable Algo Trading at any time
- inspect broker rejection retcodes and correct symbol, margin, stop-distance, or filling settings
- backtest or optimize a separately prepared strategy version in MT5 Strategy Tester
- replace the placeholder news/sentiment provider with a licensed, reliable provider while preserving the existing return contract

## What a trader cannot assume

The trader cannot assume that the bot:

- guarantees profits or prevents losses
- knows the broker's symbol suffix automatically in every environment
- can run the Python version on Linux without a Windows MT5 terminal
- can trade while MT5 is closed, disconnected, logged out, or missing market data
- automatically understands every broker's execution mode, contract specification, or session schedule
- automatically imports a complete economic calendar in the EA version
- replaces human supervision, broker due diligence, risk controls, or regulatory obligations
- recovers an interrupted process with a distributed lock or shared state
- safely supports two Python instances using the same account and magic number
- provides a complete historical backtest from this repository
- turns the React dashboard into a live control plane; its current feed is mock data unless a backend bridge is added
- safely modifies or closes arbitrary manual positions; position ownership must be checked against symbol and magic-number configuration

## News and sentiment limitation

The Python function `analyze_market_sentiment()` is currently a placeholder/mock provider unless it has been replaced locally. A production deployment must connect it to a verified economic-calendar and sentiment service, handle stale or missing responses, and use broker/server time consistently.

The EA inputs only provide a manual next-event timestamp. A timestamp alone is not proof that the event is high impact or that the data is current. During a high-impact release, the conservative operator action is to disable new entries and supervise existing positions.

## Recommended operating procedure

1. Compile or install in a demo environment.
2. Verify symbol names, digits, tick value, tick size, volume step, stop level, freeze level, and trading sessions.
3. Run at least a forward-test period across each intended symbol.
4. Confirm that logs show correct candle timing, signal reasons, lot sizing, and broker responses.
5. Test news blackout behavior with a known timestamp before enabling live execution.
6. Start with a small risk allocation and a hard external loss limit.
7. Keep the terminal, machine, credentials, and network monitored.
8. Review every trade and disable the bot immediately if behavior differs from the tested rules.

## Current project limitations

- Live MT5 compilation and broker testing must be performed on Windows with MetaEditor and a broker account.
- The Python sentiment/news integration is not production-ready until a real provider is connected.
- Trailing-stop original-risk persistence is approximate after a stop has already moved.
- The Python process is single-machine and single-process.
- The React dashboard is presently backed by mock generators and is not an authoritative execution interface.
