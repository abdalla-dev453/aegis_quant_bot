# MT5 Confluence Trading Bot

Python-driven trading bot for MetaTrader 5 combining multi-timeframe EMA
trend, RSI filtering, a pluggable sentiment engine, and ATR-based risk
management with 1:1 RR trailing stops.

## Setup

```bash
# Windows only — the MetaTrader5 package wraps the native terminal API
pip install -r requirements.txt
```

1. Open MT5, log into your (ideally **demo**) account once manually so the
   terminal has cached the session.
2. Set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` as environment variables
   (don't hardcode them in `config.py` for anything beyond local testing).
3. Adjust `TRADING_SYMBOLS` and `RISK` in `config.py` to match your broker's
   symbol names (e.g. some brokers suffix `.a`, `EURUSD.pro`, etc.) and your
   real risk tolerance.
4. Run:
   ```bash
   python main.py
   ```

## File map

| File               | Responsibility                                                               |
| ------------------ | ---------------------------------------------------------------------------- |
| `config.py`        | All settings — credentials, symbols, indicator/risk params. No side effects. |
| `data_provider.py` | MT5 connection lifecycle, reconnection, candle/account data fetching.        |
| `strategy.py`      | Indicators, mock sentiment engine, news blackout, confluence signal fusion.  |
| `execution.py`     | Lot sizing, SL/TP calculation, `order_send`, trailing stop management.       |
| `main.py`          | Async loop — polls for newly closed candles per symbol, dispatches signals.  |

## Known limitations to address before going live

1. **`analyze_market_sentiment()` is a mock.** It returns randomized
   placeholder data shaped like a real economic-calendar + NLP sentiment
   API response. Swap the function body for a real HTTP call (e.g. to
   Trading Economics, Finnhub, or a licensed news-sentiment provider) —
   keep the `SentimentReading` return contract the same so nothing else
   needs to change.
2. **No backtest harness included.** This is live/paper-execution code.
   Validate the strategy logic in `strategy.py` against historical data
   (e.g. via `backtesting.py` or a custom vectorized backtest) before
   running it against a funded account.
3. **Single-process, single-machine.** No distributed locking — don't run
   two instances of `main.py` against the same account/magic number
   simultaneously, or `max_concurrent_positions` accounting will race.
4. **`deviation_points` (slippage tolerance) and `atr_sl_multiplier` /
   `atr_tp_multiplier`** are reasonable starting defaults, not tuned
   values — backtest and adjust per symbol.

## Architecture notes

- **Multi-timeframe confluence**: H4 EMA50/200 sets directional _bias_, H1
  EMA50/200 gives the _trigger_. A signal only fires when both agree —
  this is what makes it genuinely multi-timeframe rather than checking the
  same crossover twice.
- **Never trades on a forming candle**: `data_provider.get_rates()` uses
  `copy_rates_from_pos(..., start_pos=1, ...)`, always skipping the
  currently-open candle, and `main.py`'s `LastCandleTracker` re-evaluates a
  symbol only once its H1 candle has actually closed.
- **Position sizing is broker-aware**: uses `symbol_info().trade_tick_value`
  / `trade_tick_size` rather than a hardcoded pip value, so 1.5% risk is
  accurate across FX pairs, JPY pairs, and metals alike.
