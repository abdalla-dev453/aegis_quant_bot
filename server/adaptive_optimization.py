"""
adaptive_optimization.py
------------------------
Adaptive parameter optimization system that automatically adjusts trading
parameters based on recent performance metrics.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional
from collections import deque
import json
from pathlib import Path

import pandas as pd

# Optional numpy for statistical calculations
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from config import ADAPTIVE, INDICATORS, STRATEGY, RISK
from runtime_state import read

logger = logging.getLogger("trading_bot.adaptive_optimization")


class OptimizationStatus(str, Enum):
    """Status of adaptive optimization"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    INSUFFICIENT_DATA = "insufficient_data"
    OPTIMIZING = "optimizing"


class AdjustmentDirection(str, Enum):
    """Direction of parameter adjustment"""
    INCREASE = "increase"
    DECREASE = "decrease"
    NO_CHANGE = "no_change"


@dataclass
class PerformanceMetrics:
    """Recent trading performance metrics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    profit_factor: float
    average_win: float
    average_loss: float
    max_drawdown: float
    sharpe_ratio: float
    period_start: datetime
    period_end: datetime


@dataclass
class ParameterAdjustment:
    """Record of a parameter adjustment"""
    parameter_name: str
    old_value: float
    new_value: float
    direction: AdjustmentDirection
    reason: str
    timestamp: datetime
    performance_before: PerformanceMetrics | None


class AdaptiveOptimizer:
    """
    Automatically adjusts trading parameters based on recent performance.
    """
    
    def __init__(self):
        self.enabled = ADAPTIVE.enable_adaptive_parameters
        self.optimization_window_days = ADAPTIVE.optimization_window_days
        self.min_trades_for_optimization = ADAPTIVE.min_trades_for_optimization
        
        self.adjustment_history: deque[ParameterAdjustment] = deque(maxlen=50)
        self.current_parameters: dict[str, float] = self._get_current_parameters()
        self._lock = threading.Lock()
        
        # Performance tracking
        self.performance_history: deque[PerformanceMetrics] = deque(maxlen=10)
        
        if self.enabled:
            logger.info("Adaptive optimization enabled")
        else:
            logger.info("Adaptive optimization disabled")
    
    def _get_current_parameters(self) -> dict[str, float]:
        """Get current trading parameters from config"""
        return {
            'rsi_overbought': getattr(INDICATORS, 'rsi_overbought', 70.0),
            'rsi_oversold': getattr(INDICATORS, 'rsi_oversold', 30.0),
            'sentiment_bullish_threshold': STRATEGY.sentiment_bullish_threshold,
            'sentiment_bearish_threshold': STRATEGY.sentiment_bearish_threshold,
            'risk_per_trade_pct': RISK.risk_per_trade_pct,
            'atr_sl_multiplier': RISK.atr_sl_multiplier,
            'atr_tp_multiplier': RISK.atr_tp_multiplier,
        }
    
    def analyze_recent_performance(self) -> PerformanceMetrics:
        """
        Analyze recent trading performance from the order history.
        
        Returns:
            PerformanceMetrics with recent trading statistics
        """
        try:
            state = read()
            orders = state.get('orders', [])
            
            if not orders:
                return self._empty_performance_metrics()
            
            # Filter orders within optimization window
            window_start = datetime.now(timezone.utc) - timedelta(days=self.optimization_window_days)
            recent_orders = [
                order for order in orders
                if datetime.fromisoformat(order.get('timestamp', datetime.now(timezone.utc).isoformat())) >= window_start
            ]
            
            if len(recent_orders) < self.min_trades_for_optimization:
                logger.info(f"Insufficient trades for optimization ({len(recent_orders)} < {self.min_trades_for_optimization})")
                return self._empty_performance_metrics()
            
            # Calculate metrics
            winning_trades = [o for o in recent_orders if o.get('pnl', 0) > 0]
            losing_trades = [o for o in recent_orders if o.get('pnl', 0) < 0]
            
            total_trades = len(recent_orders)
            wins = len(winning_trades)
            losses = len(losing_trades)
            
            win_rate = wins / total_trades if total_trades > 0 else 0.0
            
            total_profit = sum(o.get('pnl', 0) for o in winning_trades)
            total_loss = abs(sum(o.get('pnl', 0) for o in losing_trades))
            
            profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
            
            avg_win = total_profit / wins if wins > 0 else 0.0
            avg_loss = total_loss / losses if losses > 0 else 0.0
            
            # Calculate max drawdown
            equity_curve = self._calculate_equity_curve(recent_orders)
            max_drawdown = self._calculate_max_drawdown(equity_curve)
            
            # Calculate Sharpe ratio (simplified)
            returns = [o.get('pnl', 0) for o in recent_orders]
            sharpe_ratio = self._calculate_sharpe_ratio(returns) if returns else 0.0
            
            metrics = PerformanceMetrics(
                total_trades=total_trades,
                winning_trades=wins,
                losing_trades=losses,
                win_rate=win_rate,
                total_profit=total_profit,
                total_loss=total_loss,
                profit_factor=profit_factor,
                average_win=avg_win,
                average_loss=avg_loss,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                period_start=window_start,
                period_end=datetime.now(timezone.utc)
            )
            
            # Store in history
            self.performance_history.append(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error analyzing performance: {e}")
            return self._empty_performance_metrics()
    
    def _empty_performance_metrics(self) -> PerformanceMetrics:
        """Return empty performance metrics"""
        now = datetime.now(timezone.utc)
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_profit=0.0,
            total_loss=0.0,
            profit_factor=0.0,
            average_win=0.0,
            average_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            period_start=now,
            period_end=now
        )
    
    def _calculate_equity_curve(self, orders: list[dict]) -> list[float]:
        """Calculate equity curve from order history"""
        equity = [0.0]
        running_balance = 0.0
        
        for order in orders:
            running_balance += order.get('pnl', 0)
            equity.append(running_balance)
        
        return equity
    
    def _calculate_max_drawdown(self, equity_curve: list[float]) -> float:
        """Calculate maximum drawdown from equity curve"""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]
        max_drawdown = 0.0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            
            drawdown = (peak - value) / peak if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _calculate_sharpe_ratio(self, returns: list[float]) -> float:
        """Calculate simplified Sharpe ratio"""
        if not returns or len(returns) < 2:
            return 0.0
        
        if not NUMPY_AVAILABLE:
            # Fallback calculation without numpy
            import statistics
            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
            if std_return == 0:
                return 0.0
            return mean_return / std_return * 15.87  # Approximate annualization
        
        returns_array = np.array(returns)
        
        if np.std(returns_array) == 0:
            return 0.0
        
        return np.mean(returns_array) / np.std(returns_array) * np.sqrt(252)  # Annualized
    
    def determine_adjustments(self, performance: PerformanceMetrics) -> list[ParameterAdjustment]:
        """
        Determine necessary parameter adjustments based on performance.
        
        Args:
            performance: Current performance metrics
            
        Returns:
            List of recommended parameter adjustments
        """
        if not self.enabled:
            return []
        
        if performance.total_trades < self.min_trades_for_optimization:
            logger.info("Insufficient trades for parameter adjustment")
            return []
        
        adjustments = []
        
        # Win rate adjustments
        if performance.win_rate < ADAPTIVE.win_rate_lower_threshold:
            # Poor performance - tighten criteria
            adjustments.extend(self._tighten_criteria(performance))
        elif performance.win_rate > ADAPTIVE.win_rate_upper_threshold:
            # Good performance - loosen criteria slightly
            adjustments.extend(self._loosen_criteria(performance))
        
        # Profit factor adjustments
        if performance.profit_factor < ADAPTIVE.profit_factor_threshold:
            # Poor risk/reward - adjust risk management
            adjustments.extend(self._adjust_risk_management(performance))
        
        # Drawdown adjustments
        if performance.max_drawdown > 0.15:  # 15% drawdown threshold
            # High drawdown - reduce risk
            adjustments.extend(self._reduce_risk(performance))
        
        return adjustments
    
    def _tighten_criteria(self, performance: PerformanceMetrics) -> list[ParameterAdjustment]:
        """Generate adjustments to tighten entry criteria"""
        adjustments = []
        
        # Tighten RSI thresholds
        if self.current_parameters['rsi_overbought'] < 75:
            new_rsi_overbought = min(80, self.current_parameters['rsi_overbought'] + ADAPTIVE.rsi_adjustment_range)
            adjustments.append(ParameterAdjustment(
                parameter_name='rsi_overbought',
                old_value=self.current_parameters['rsi_overbought'],
                new_value=new_rsi_overbought,
                direction=AdjustmentDirection.INCREASE,
                reason=f"Low win rate ({performance.win_rate:.1%}) - tightening overbought threshold",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['rsi_overbought'] = new_rsi_overbought
        
        if self.current_parameters['rsi_oversold'] > 25:
            new_rsi_oversold = max(20, self.current_parameters['rsi_oversold'] - ADAPTIVE.rsi_adjustment_range)
            adjustments.append(ParameterAdjustment(
                parameter_name='rsi_oversold',
                old_value=self.current_parameters['rsi_oversold'],
                new_value=new_rsi_oversold,
                direction=AdjustmentDirection.DECREASE,
                reason=f"Low win rate ({performance.win_rate:.1%}) - tightening oversold threshold",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['rsi_oversold'] = new_rsi_oversold
        
        # Tighten sentiment thresholds
        if self.current_parameters['sentiment_bullish_threshold'] < 0.7:
            new_bullish_threshold = min(0.8, self.current_parameters['sentiment_bullish_threshold'] + ADAPTIVE.sentiment_adjustment_range)
            adjustments.append(ParameterAdjustment(
                parameter_name='sentiment_bullish_threshold',
                old_value=self.current_parameters['sentiment_bullish_threshold'],
                new_value=new_bullish_threshold,
                direction=AdjustmentDirection.INCREASE,
                reason=f"Low win rate ({performance.win_rate:.1%}) - requiring stronger bullish sentiment",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['sentiment_bullish_threshold'] = new_bullish_threshold
        
        if self.current_parameters['sentiment_bearish_threshold'] > -0.7:
            new_bearish_threshold = max(-0.8, self.current_parameters['sentiment_bearish_threshold'] - ADAPTIVE.sentiment_adjustment_range)
            adjustments.append(ParameterAdjustment(
                parameter_name='sentiment_bearish_threshold',
                old_value=self.current_parameters['sentiment_bearish_threshold'],
                new_value=new_bearish_threshold,
                direction=AdjustmentDirection.DECREASE,
                reason=f"Low win rate ({performance.win_rate:.1%}) - requiring stronger bearish sentiment",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['sentiment_bearish_threshold'] = new_bearish_threshold
        
        return adjustments
    
    def _loosen_criteria(self, performance: PerformanceMetrics) -> list[ParameterAdjustment]:
        """Generate adjustments to loosen entry criteria"""
        adjustments = []
        
        # Loosen RSI thresholds slightly
        if self.current_parameters['rsi_overbought'] > 65:
            new_rsi_overbought = max(65, self.current_parameters['rsi_overbought'] - ADAPTIVE.rsi_adjustment_range / 2)
            adjustments.append(ParameterAdjustment(
                parameter_name='rsi_overbought',
                old_value=self.current_parameters['rsi_overbought'],
                new_value=new_rsi_overbought,
                direction=AdjustmentDirection.DECREASE,
                reason=f"High win rate ({performance.win_rate:.1%}) - loosening overbought threshold",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['rsi_overbought'] = new_rsi_overbought
        
        if self.current_parameters['rsi_oversold'] < 35:
            new_rsi_oversold = min(35, self.current_parameters['rsi_oversold'] + ADAPTIVE.rsi_adjustment_range / 2)
            adjustments.append(ParameterAdjustment(
                parameter_name='rsi_oversold',
                old_value=self.current_parameters['rsi_oversold'],
                new_value=new_rsi_oversold,
                direction=AdjustmentDirection.INCREASE,
                reason=f"High win rate ({performance.win_rate:.1%}) - loosening oversold threshold",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['rsi_oversold'] = new_rsi_oversold
        
        return adjustments
    
    def _adjust_risk_management(self, performance: PerformanceMetrics) -> list[ParameterAdjustment]:
        """Generate adjustments to improve risk/reward ratio"""
        adjustments = []
        
        # Increase take profit multiplier
        if self.current_parameters['atr_tp_multiplier'] < 4.0:
            new_tp_multiplier = min(4.0, self.current_parameters['atr_tp_multiplier'] + 0.5)
            adjustments.append(ParameterAdjustment(
                parameter_name='atr_tp_multiplier',
                old_value=self.current_parameters['atr_tp_multiplier'],
                new_value=new_tp_multiplier,
                direction=AdjustmentDirection.INCREASE,
                reason=f"Low profit factor ({performance.profit_factor:.2f}) - increasing take profit target",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['atr_tp_multiplier'] = new_tp_multiplier
        
        return adjustments
    
    def _reduce_risk(self, performance: PerformanceMetrics) -> list[ParameterAdjustment]:
        """Generate adjustments to reduce risk"""
        adjustments = []
        
        # Reduce risk per trade
        if self.current_parameters['risk_per_trade_pct'] > 0.5:
            new_risk_pct = max(0.5, self.current_parameters['risk_per_trade_pct'] - ADAPTIVE.risk_adjustment_range)
            adjustments.append(ParameterAdjustment(
                parameter_name='risk_per_trade_pct',
                old_value=self.current_parameters['risk_per_trade_pct'],
                new_value=new_risk_pct,
                direction=AdjustmentDirection.DECREASE,
                reason=f"High drawdown ({performance.max_drawdown:.1%}) - reducing risk per trade",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['risk_per_trade_pct'] = new_risk_pct
        
        # Increase stop loss multiplier (wider stops to reduce premature exits)
        if self.current_parameters['atr_sl_multiplier'] < 2.0:
            new_sl_multiplier = min(2.0, self.current_parameters['atr_sl_multiplier'] + 0.25)
            adjustments.append(ParameterAdjustment(
                parameter_name='atr_sl_multiplier',
                old_value=self.current_parameters['atr_sl_multiplier'],
                new_value=new_sl_multiplier,
                direction=AdjustmentDirection.INCREASE,
                reason=f"High drawdown ({performance.max_drawdown:.1%}) - widening stop loss",
                timestamp=datetime.now(timezone.utc),
                performance_before=performance
            ))
            self.current_parameters['atr_sl_multiplier'] = new_sl_multiplier
        
        return adjustments
    
    def apply_adjustments(self, adjustments: list[ParameterAdjustment]) -> bool:
        """
        Apply parameter adjustments (Note: This would need to update actual config).
        
        Args:
            adjustments: List of adjustments to apply
            
        Returns:
            True if adjustments were applied successfully
        """
        if not adjustments:
            return False
        
        with self._lock:
            for adjustment in adjustments:
                self.adjustment_history.append(adjustment)
                logger.info(
                    f"Adjusted {adjustment.parameter_name}: {adjustment.old_value:.3f} -> "
                    f"{adjustment.new_value:.3f} ({adjustment.direction.value}) - {adjustment.reason}"
                )
        
        # Note: In a real implementation, this would update the actual configuration
        # For now, we just track the adjustments in memory
        logger.info(f"Applied {len(adjustments)} parameter adjustments")
        
        return True
    
    def run_optimization_cycle(self) -> dict[str, Any]:
        """
        Run a complete optimization cycle.
        
        Returns:
            Summary of optimization results
        """
        if not self.enabled:
            return {
                "status": OptimizationStatus.DISABLED.value,
                "adjustments_made": 0,
                "performance": None
            }
        
        try:
            # Analyze recent performance
            performance = self.analyze_recent_performance()
            
            if performance.total_trades < self.min_trades_for_optimization:
                return {
                    "status": OptimizationStatus.INSUFFICIENT_DATA.value,
                    "adjustments_made": 0,
                    "performance": {
                        "total_trades": performance.total_trades,
                        "win_rate": performance.win_rate,
                        "profit_factor": performance.profit_factor
                    }
                }
            
            # Determine necessary adjustments
            adjustments = self.determine_adjustments(performance)
            
            # Apply adjustments
            if adjustments:
                self.apply_adjustments(adjustments)
            
            return {
                "status": OptimizationStatus.ENABLED.value,
                "adjustments_made": len(adjustments),
                "performance": {
                    "total_trades": performance.total_trades,
                    "win_rate": performance.win_rate,
                    "profit_factor": performance.profit_factor,
                    "max_drawdown": performance.max_drawdown
                },
                "adjustments": [
                    {
                        "parameter": adj.parameter_name,
                        "old_value": adj.old_value,
                        "new_value": adj.new_value,
                        "direction": adj.direction.value,
                        "reason": adj.reason
                    }
                    for adj in adjustments
                ]
            }
            
        except Exception as e:
            logger.error(f"Error in optimization cycle: {e}")
            return {
                "status": "error",
                "error": str(e),
                "adjustments_made": 0
            }
    
    def get_optimization_status(self) -> dict[str, Any]:
        """Get current optimization status and history"""
        with self._lock:
            return {
                "enabled": self.enabled,
                "current_parameters": self.current_parameters,
                "recent_performance": [
                    {
                        "total_trades": p.total_trades,
                        "win_rate": p.win_rate,
                        "profit_factor": p.profit_factor,
                        "max_drawdown": p.max_drawdown,
                        "period": f"{p.period_start.date()} to {p.period_end.date()}"
                    }
                    for p in list(self.performance_history)[-5:]
                ],
                "recent_adjustments": [
                    {
                        "parameter": adj.parameter_name,
                        "old_value": adj.old_value,
                        "new_value": adj.new_value,
                        "direction": adj.direction.value,
                        "reason": adj.reason,
                        "timestamp": adj.timestamp.isoformat()
                    }
                    for adj in list(self.adjustment_history)[-10:]
                ],
                "optimization_window_days": self.optimization_window_days,
                "min_trades_for_optimization": self.min_trades_for_optimization
            }
    
    def save_adjustment_history(self, file_path: str = "parameter_adjustments.json"):
        """Save adjustment history to file"""
        try:
            history_data = [
                {
                    "parameter_name": adj.parameter_name,
                    "old_value": adj.old_value,
                    "new_value": adj.new_value,
                    "direction": adj.direction.value,
                    "reason": adj.reason,
                    "timestamp": adj.timestamp.isoformat(),
                    "performance_before": {
                        "total_trades": adj.performance_before.total_trades,
                        "win_rate": adj.performance_before.win_rate,
                        "profit_factor": adj.performance_before.profit_factor
                    } if adj.performance_before else None
                }
                for adj in self.adjustment_history
            ]
            
            with open(file_path, 'w') as f:
                json.dump(history_data, f, indent=2)
            
            logger.info(f"Saved adjustment history to {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving adjustment history: {e}")


# Global instance
adaptive_optimizer = AdaptiveOptimizer()