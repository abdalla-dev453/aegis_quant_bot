"""
main.py
-------
Asynchronous execution loop. Runs continuously, polling for newly closed
H1 candles per symbol and only re-evaluating a symbol's signal once its
candle has actually closed (never mid-candle, which would repaint).

Usage:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import signal
import socket
import sys
import threading
import time

import pandas as pd
from adaptive_optimization import adaptive_optimizer
from advanced_technical_analysis import (
    analyze_trend_maturity,
    analyze_volume,
    calculate_adx,
    calculate_macd,
    compute_advanced_indicators,
    detect_market_regime,
    detect_support_resistance,
)
from ai_engine import ProposalAction, propose_trade, validate_ai_configuration
from config import (
    ADAPTIVE,
    ADVANCED_ANALYSIS,
    ADVANCED_RISK,
    AI,
    CANDLES_TO_FETCH,
    CREDENTIALS,
    DEPLOYMENT,
    EXECUTION,
    INDICATORS,
    INITIAL_BACKOFF_SECONDS,
    LOGGING,
    MAX_BACKOFF_SECONDS,
    PREDICTION,
    RISK,
    STRATEGY,
    TIMEFRAME_BIAS,
    TIMEFRAME_TRIGGER,
    TRADING_SYMBOLS,
)
from data_provider import (
    MT5ConnectionError,
    get_rates,
    initialize_connection,
    mt5,
    mt5_operation_lock,
    resolve_and_validate_symbols,
    resolved_symbol,
    shutdown_connection,
)
from execution import manage_trailing_stops, place_order
from intelligent_position_manager import IntelligentPositionManager
from news_provider import get_latest_high_impact_news
from portfolio_risk_manager import portfolio_risk_manager
from prediction_engine import (
    PatternRecognitionEngine,
    PricePredictionEngine,
    VolatilityForecaster,
)
from runtime_state import (
    add_log,
    control_state,
    record_order,
    record_proposal,
    update,
)
from self_healing import data_quality_checker, self_healing_manager
from strategy import TradeDirection, compute_indicators, generate_signal

logger = logging.getLogger("trading_bot.main")

# Initialize advanced systems
prediction_engine = PricePredictionEngine()
pattern_engine = PatternRecognitionEngine()
volatility_forecaster = VolatilityForecaster()
position_manager = IntelligentPositionManager()


def _systemd_notify(message: str) -> None:
    notify_socket = os.getenv("NOTIFY_SOCKET")
    if not notify_socket:
        return
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
        notifier.sendto(message.encode(), notify_socket)


def notify_systemd(message: str) -> None:
    try:
        _systemd_notify(message)
    except OSError:
        logger.debug("systemd notification failed", exc_info=True)


def start_dashboard_api() -> None:
    import uvicorn
    from api import app

    config = uvicorn.Config(
        app,
        host=DEPLOYMENT.api_host,
        port=DEPLOYMENT.api_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    api_thread = threading.Thread(target=server.run, daemon=True)
    api_thread.start()

    for _ in range(100):
        if server.started:
            logger.info(
                "Dashboard API listening on http://%s:%s",
                DEPLOYMENT.api_host,
                DEPLOYMENT.api_port,
            )
            return
        if not api_thread.is_alive():
            raise RuntimeError("Dashboard API failed to start")
        time.sleep(0.1)
    raise RuntimeError("Dashboard API did not become ready within 10 seconds")


def setup_logging() -> None:
    level = getattr(logging, LOGGING.level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    root = logging.getLogger("trading_bot")
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOGGING.log_file, maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)


class LastCandleTracker:
    """Tracks the last-seen closed candle timestamp per symbol to avoid
    re-evaluating the same H1 candle repeatedly while we wait for the next
    one to close."""

    def __init__(self) -> None:
        self._last_seen: dict[str, pd.Timestamp] = {}

    def is_new_candle(self, symbol: str, candle_time: pd.Timestamp) -> bool:
        prev = self._last_seen.get(symbol)
        return prev is None or candle_time > prev

    def mark_seen(self, symbol: str, candle_time: pd.Timestamp) -> None:
        self._last_seen[symbol] = candle_time


async def evaluate_symbol(symbol: str, tracker: LastCandleTracker) -> None:
    """Fetch data, check for a new closed H1 candle, and act on a fresh signal."""
    try:
        # Fetch H1 and H4 concurrently — the two calls are independent and
        # each spends most of its time blocked on the MT5 IPC call.
        df_h1_raw, df_h4_raw = await asyncio.gather(
            asyncio.to_thread(get_rates, symbol, TIMEFRAME_TRIGGER, CANDLES_TO_FETCH),
            asyncio.to_thread(get_rates, symbol, TIMEFRAME_BIAS, CANDLES_TO_FETCH),
        )

        # NaN/NaT guard: a garbage timestamp must not corrupt the tracker
        latest_candle_time = pd.Timestamp(df_h1_raw.index[-1])
        if pd.isna(latest_candle_time):
            logger.warning("%s: latest candle timestamp is NaT — skipping cycle.", symbol)
            return

        if not tracker.is_new_candle(symbol, latest_candle_time):
            return  # already evaluated this candle; nothing to do yet

        df_h1, df_h4 = await asyncio.gather(
            asyncio.to_thread(compute_indicators, df_h1_raw),
            asyncio.to_thread(compute_indicators, df_h4_raw),
        )

        if df_h1.empty or df_h4.empty:
            logger.warning("%s: not enough warmed-up candle data yet, skipping.", symbol)
            tracker.mark_seen(symbol, latest_candle_time)
            return

        # Validate data quality
        data_valid, data_error = data_quality_checker.validate_dataframe(df_h1, symbol)
        if not data_valid:
            logger.warning("%s: data quality check failed: %s", symbol, data_error)
            tracker.mark_seen(symbol, latest_candle_time)
            return

        # Add advanced indicators if enabled
        if ADVANCED_ANALYSIS.use_adx or ADVANCED_ANALYSIS.use_macd:
            df_h1 = await asyncio.to_thread(compute_advanced_indicators, df_h1)
            df_h4 = await asyncio.to_thread(compute_advanced_indicators, df_h4)

        tracker.mark_seen(symbol, latest_candle_time)
        h1_last, h4_last = df_h1.iloc[-1], df_h4.iloc[-1]
        
        # Advanced market analysis
        market_regime = await asyncio.to_thread(detect_market_regime, df_h1)
        sr_levels = await asyncio.to_thread(detect_support_resistance, df_h1)
        trend_maturity = await asyncio.to_thread(analyze_trend_maturity, df_h1, df_h4)
        volume_analysis = await asyncio.to_thread(analyze_volume, df_h1) if ADVANCED_ANALYSIS.use_volume_confirmation else None
        
        # Build enhanced market context
        market_context = {
            "candle_time_utc": latest_candle_time.isoformat(),
            "trigger_timeframe": TIMEFRAME_TRIGGER,
            "bias_timeframe": TIMEFRAME_BIAS,
            "h1": {
                "close": float(h1_last["close"]),
                "ema_fast": float(h1_last[f"ema_{INDICATORS.ema_fast}"]),
                "ema_slow": float(h1_last[f"ema_{INDICATORS.ema_slow}"]),
                "rsi": float(h1_last["rsi"]),
                "atr": float(h1_last["atr"]),
            },
            "h4": {
                "close": float(h4_last["close"]),
                "ema_fast": float(h4_last[f"ema_{INDICATORS.ema_fast}"]),
                "ema_slow": float(h4_last[f"ema_{INDICATORS.ema_slow}"]),
                "rsi": float(h4_last["rsi"]),
                "atr": float(h4_last["atr"]),
            },
            "advanced_analysis": {
                "market_regime": market_regime.regime.value,
                "regime_confidence": market_regime.confidence,
                "support_levels": sr_levels.support_levels,
                "resistance_levels": sr_levels.resistance_levels,
                "trend_maturity": trend_maturity.stage,
                "trend_strength": trend_maturity.strength_score,
                "volume_surge": volume_analysis.surge_detected if volume_analysis else False,
                "volume_ratio": volume_analysis.volume_ratio if volume_analysis else 0.0,
            }
        }
        
        # Add ADX and MACD if available
        if ADVANCED_ANALYSIS.use_adx and f'adx_{ADVANCED_ANALYSIS.adx_period}' in df_h1.columns:
            adx_result = await asyncio.to_thread(calculate_adx, df_h1)
            market_context["advanced_analysis"]["adx"] = adx_result.adx_value
            market_context["advanced_analysis"]["trend_strength"] = adx_result.trend_strength.value
        
        if ADVANCED_ANALYSIS.use_macd and 'macd' in df_h1.columns:
            macd_result = await asyncio.to_thread(calculate_macd, df_h1)
            market_context["advanced_analysis"]["macd_signal"] = macd_result.signal_type
        
        # Pattern recognition if enabled
        if PREDICTION.enable_pattern_detection:
            patterns = await asyncio.to_thread(pattern_engine.detect_patterns, df_h1)
            market_context["advanced_analysis"]["detected_patterns"] = [
                {"pattern": p.pattern_name, "confidence": p.confidence, "direction": p.direction.value}
                for p in patterns
            ]
        
        # Volatility forecasting if enabled
        if PREDICTION.enable_volatility_forecasting:
            volatility_forecast = await asyncio.to_thread(volatility_forecaster.forecast_volatility, df_h1)
            market_context["advanced_analysis"]["volatility_forecast"] = {
                "regime": volatility_forecast.volatility_regime,
                "expected_volatility": volatility_forecast.expected_volatility,
                "breakout_probability": volatility_forecast.breakout_probability
            }
        
        # Price prediction if enabled
        if PREDICTION.enable_price_prediction:
            price_prediction = await asyncio.to_thread(prediction_engine.predict_price_move, df_h1)
            market_context["advanced_analysis"]["price_prediction"] = {
                "direction": price_prediction.direction.value,
                "confidence": price_prediction.confidence,
                "target_price": price_prediction.target_price
            }
        
        news_result = await asyncio.to_thread(get_latest_high_impact_news, 10, 24)
        proposal = await propose_trade(
            symbol, market_context, news_result.items, news_result.warning
        )
        direction = {
            ProposalAction.BUY: TradeDirection.BUY,
            ProposalAction.SELL: TradeDirection.SELL,
            ProposalAction.HOLD: TradeDirection.NONE,
        }[proposal.action]
        technical = 1.0 if direction == TradeDirection.BUY else -1.0 if direction == TradeDirection.SELL else 0.0
        logger.info("%s | candle=%s | AI action=%s | confidence=%.2f | reason=%s", symbol, latest_candle_time, proposal.action.value, proposal.confidence_score, proposal.reasoning)
        update(
            last_signal={
                "composite": technical,
                "label": proposal.action.value,
                "technical": technical,
                "sentiment": 0.0,
                "momentum": technical,
            }
        )
        add_log("INFO", f"{symbol} AI {proposal.action.value}: {proposal.reasoning}")

        control = control_state()
        proposal_record = {
            "symbol": symbol,
            "action": proposal.action.value,
            "volume": proposal.volume,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "confidence_score": proposal.confidence_score,
            "reasoning": proposal.reasoning,
            "status": "received",
            "candle_time": latest_candle_time.isoformat(),
        }

        if control["status"] != "RUNNING" or not control["entriesAllowed"]:
            proposal_record["status"] = "blocked"
            proposal_record["blocked_by"] = f"control={control['status']}"
            record_proposal(proposal_record)
            add_log("INFO", f"{symbol} proposal blocked by control={control['status']}")
            return

        if direction in (TradeDirection.BUY, TradeDirection.SELL):
            signal = generate_signal(symbol, df_h1, df_h4)
            if news_result.warning:
                signal.direction = TradeDirection.NONE
                signal.reason = f"News feed warning: {news_result.warning}"
            if signal.direction != direction:
                proposal_record["status"] = "blocked"
                proposal_record["blocked_by"] = "deterministic_strategy"
                proposal_record["signal_reason"] = signal.reason
                record_proposal(proposal_record)
                add_log("INFO", f"{symbol} proposal blocked by deterministic gate: {signal.reason}")
                return

            # Portfolio risk check
            if ADVANCED_RISK.enable_portfolio_risk:
                portfolio_allowed, portfolio_reason = await asyncio.to_thread(
                    portfolio_risk_manager.check_pre_trade_risk,
                    symbol, direction.value, proposal.volume
                )
                if not portfolio_allowed:
                    proposal_record["status"] = "blocked"
                    proposal_record["blocked_by"] = "portfolio_risk"
                    proposal_record["signal_reason"] = portfolio_reason
                    record_proposal(proposal_record)
                    add_log("INFO", f"{symbol} proposal blocked by portfolio risk: {portfolio_reason}")
                    return

            # Volatility-based position sizing adjustment
            adjusted_volume = proposal.volume
            if ADVANCED_RISK.enable_volatility_adjusted_sizing:
                vol_adjustment = await asyncio.to_thread(
                    position_manager.calculate_volatility_adjusted_size,
                    symbol, proposal.volume, df_h1
                )
                adjusted_volume = vol_adjustment.adjusted_size
                logger.info(f"{symbol} volume adjusted: {proposal.volume} -> {adjusted_volume} ({vol_adjustment.reason})")

            record_proposal(proposal_record)

            audit_context = {
                "candle_time": latest_candle_time.isoformat(),
                "ai_confidence_score": proposal.confidence_score,
                "ai_market_context": market_context,
                "live_news": news_result.items,
                "news_warning": news_result.warning,
                "advanced_analysis": market_context.get("advanced_analysis", {}),
                "volume_adjustment": adjusted_volume != proposal.volume
            }
            result = await asyncio.to_thread(
                place_order, symbol, direction, float(h1_last["atr"]), proposal.reasoning,
                audit_context, adjusted_volume, proposal.stop_loss, proposal.take_profit,
            )
            if result and result.get("order") and EXECUTION.live_orders_enabled:
                record_order(
                    {
                        "ticket": int(result["order"]),
                        "symbol": symbol,
                        "direction": direction.value,
                        "fill_price": float(result.get("price") or 0.0),
                        "volume": float(result.get("volume") or 0.0),
                        "sl": float(result.get("sl") or 0.0),
                        "tp": float(result.get("tp") or 0.0),
                        "atr": float(h1_last["atr"]),
                        "reason": proposal.reasoning,
                        "pnl": 0.0,
                        "status": "filled",
                    }
                )
        else:
            record_proposal(proposal_record)

    except MT5ConnectionError as e:
        logger.error("%s: connection error during evaluation: %s", symbol, e)
    except Exception:
        logger.exception("%s: unexpected error during evaluation", symbol)


class ErrorBackoff:
    """Circuit-breaker-ish backoff: on consecutive failures, progressively
    delay the loop so a dead feed doesn't spin at full polling rate."""

    def __init__(self) -> None:
        self._consecutive = 0

    def record_success(self) -> None:
        self._consecutive = 0

    def record_failure(self) -> float:
        self._consecutive += 1
        return min(
            INITIAL_BACKOFF_SECONDS * (2 ** min(self._consecutive - 1, 6)),
            MAX_BACKOFF_SECONDS,
        )


async def trading_loop(stop_event: asyncio.Event) -> None:
    tracker = LastCandleTracker()
    backoff = ErrorBackoff()

    while not stop_event.is_set():
        if mt5 is None:
            notify_systemd("WATCHDOG=1")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                continue
            break

        had_error = False
        if not stop_event.is_set():
            results = await asyncio.gather(
                *(
                    evaluate_symbol(resolved_symbol(sym_cfg.name), tracker)
                    for sym_cfg in TRADING_SYMBOLS
                ),
                return_exceptions=True,
            )
            for sym_cfg, result in zip(TRADING_SYMBOLS, results):
                if isinstance(result, MT5ConnectionError):
                    had_error = True
                    logger.error("%s: connection error: %s", sym_cfg.name, result)
                    # Attempt self-healing for connection errors
                    self_healing_manager.diagnose_and_recover(result, {"symbol": sym_cfg.name})
                elif isinstance(result, Exception):
                    had_error = True
                    logger.exception("%s: unexpected error in loop", sym_cfg.name, exc_info=result)
                    # Attempt self-healing for general errors
                    self_healing_manager.diagnose_and_recover(result, {"symbol": sym_cfg.name})
                else:
                    backoff.record_success()

        try:
            await asyncio.to_thread(manage_trailing_stops)
            
            # Intelligent position management
            if ADVANCED_RISK.enable_portfolio_risk:
                portfolio_analysis = await asyncio.to_thread(portfolio_risk_manager.analyze_portfolio)
                if portfolio_analysis.overall_health.value in ["danger", "critical"]:
                    logger.warning("Portfolio health %s: %s", portfolio_analysis.overall_health.value, portfolio_analysis.risk_summary)
                    add_log("WARN", f"Portfolio health: {portfolio_analysis.overall_health.value} - {portfolio_analysis.risk_summary}")
                
                # Intelligent position analysis
                market_data = {
                    "market_regime": portfolio_analysis.overall_health.value,
                    "proximity_to_level": 0.5,  # Placeholder
                    "data_quality": 1.0
                }
                position_analyses = await asyncio.to_thread(position_manager.analyze_all_positions, market_data)
                for analysis in position_analyses:
                    if analysis.recommendation.value != "hold":
                        logger.info("Position %d %s: %s - %s", analysis.ticket, analysis.symbol, 
                                   analysis.recommendation.value, analysis.reasoning)
            
            # Adaptive optimization check (periodic)
            if ADAPTIVE.enable_adaptive_parameters:
                # Run optimization every 24 hours or after certain number of trades
                optimization_result = await asyncio.to_thread(adaptive_optimizer.run_optimization_cycle)
                if optimization_result.get("adjustments_made", 0) > 0:
                    logger.info("Adaptive optimization: %d adjustments made", optimization_result["adjustments_made"])
                    add_log("INFO", f"Adaptive optimization completed: {optimization_result['adjustments_made']} adjustments")
                    
        except MT5ConnectionError as e:
            logger.error("Position management failed: %s", e)
            # Attempt self-healing
            self_healing_manager.diagnose_and_recover(e, {"component": "position_management"})
        except Exception:
            logger.exception("Unexpected error while managing positions")

        notify_systemd("WATCHDOG=1")

        # Periodic MT5 connection health check (every ~5 minutes)
        if not hasattr(trading_loop, "_last_connection_check"):
            trading_loop._last_connection_check = 0.0
        import time as time_mod
        if time_mod.monotonic() - trading_loop._last_connection_check > 300:
            trading_loop._last_connection_check = time_mod.monotonic()
            try:
                with mt5_operation_lock():
                    if mt5.terminal_info() is None:
                        logger.warning("MT5 terminal connection lost — attempting reconnect")
                        initialize_connection()
                        update(connected=True)
            except Exception:
                logger.debug("MT5 health check failed", exc_info=True)

        poll = STRATEGY.loop_poll_seconds
        if had_error:
            extra = backoff.record_failure()
            logger.warning("Loop errors — backing off an extra %.1fs.", extra)
            poll += extra

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll)
        except asyncio.TimeoutError:
            pass  # normal — just means it's time to poll again


async def main() -> None:
    setup_logging()
    try:
        validate_ai_configuration()
        EXECUTION.validate()
        DEPLOYMENT.validate()
        
        # Validate live trading requirements
        if EXECUTION.live_orders_enabled:
            CREDENTIALS.validate_live_trade_config()
            logger.info("Live trading mode enabled - credentials validated")
        else:
            logger.info("Paper trading mode - no live credentials required")
    except ValueError as exc:
        logger.critical("Initialization aborted: %s", exc)
        raise SystemExit(1) from exc
    logger.info(
        "Starting AI trading bot | mode=%s | model=%s | symbols=%s | risk/trade=%.2f%%",
        EXECUTION.mode,
        AI.model,
        [s.name for s in TRADING_SYMBOLS],
        RISK.risk_per_trade_pct,
    )

    start_dashboard_api()
    notify_systemd("READY=1")
    
    # Initialize MT5 connection
    try:
        initialize_connection()
        resolve_and_validate_symbols()
        update(connected=True)
        logger.info("MT5 connection established and symbols validated")
    except MT5ConnectionError as e:
        if EXECUTION.live_orders_enabled:
            logger.critical("Live mode requires MT5 connection at startup: %s", e)
            raise SystemExit(1) from e
        logger.warning("MT5 unavailable at startup (paper mode); will retry in loop: %s", e)
    except Exception as e:
        logger.error("Unexpected error during MT5 initialization: %s", e)
        if EXECUTION.live_orders_enabled:
            raise SystemExit(1) from e

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig_name):
            try:
                loop.add_signal_handler(getattr(signal, sig_name), stop_event.set)
            except NotImplementedError:
                # add_signal_handler isn't available on Windows for SIGTERM in
                # some Python versions — fall back to default handling there.
                pass

    try:
        await trading_loop(stop_event)
    finally:
        logger.info("Shutting down...")
        notify_systemd("STOPPING=1")
        update(connected=False)
        shutdown_connection()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
