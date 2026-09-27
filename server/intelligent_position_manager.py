"""
intelligent_position_manager.py
--------------------------------
Intelligent position management system for dynamic exit strategies,
adaptive position sizing, and smart stop management.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import pandas as pd
from advanced_technical_analysis import (
    MarketRegime,
)
from config import ADVANCED_RISK, RISK
from data_provider import ensure_connected, get_open_positions, mt5

logger = logging.getLogger("trading_bot.intelligent_position_manager")


class ExitDecision(str, Enum):
    """Position exit decision types"""
    HOLD = "hold"
    EXIT_EARLY = "exit_early"
    TIGHTEN_STOPS = "tighten_stops"
    MOVE_BREAKEVEN = "move_breakeven"
    PARTIAL_EXIT = "partial_exit"


class PositionHealth(str, Enum):
    """Health status of a position"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class PositionAnalysis:
    """Analysis of a single position"""
    ticket: int
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    time_in_position: timedelta
    health: PositionHealth
    recommendation: ExitDecision
    reasoning: str
    suggested_stop: float | None
    suggested_take_profit: float | None
    confidence: float


@dataclass
class VolatilityAdjustment:
    """Volatility-based position sizing adjustment"""
    symbol: str
    base_size: float
    adjusted_size: float
    volatility_ratio: float
    adjustment_factor: float
    reason: str


class IntelligentPositionManager:
    """
    Advanced position management with dynamic exit strategies and 
    volatility-based sizing adjustments.
    """
    
    def __init__(self):
        self.position_history: deque[PositionAnalysis] = deque(maxlen=100)
        self.exit_decisions: deque[tuple[int, ExitDecision, str]] = deque(maxlen=50)
        self._lock = threading.Lock()
        
        logger.info("Intelligent position manager initialized")
    
    def analyze_position(self, position: Any, market_data: dict[str, Any]) -> PositionAnalysis:
        """
        Analyze a position and provide intelligent management recommendations.
        
        Args:
            position: MT5 position object
            market_data: Current market data and analysis
            
        Returns:
            PositionAnalysis with recommendations
        """
        try:
            ticket = position.ticket
            symbol = position.symbol
            direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
            entry_price = position.price_open
            current_price = position.price_current
            
            # Calculate PnL
            if direction == "BUY":
                unrealized_pnl = (current_price - entry_price) * position.volume
            else:
                unrealized_pnl = (entry_price - current_price) * position.volume
            
            unrealized_pnl_pct = (unrealized_pnl / (entry_price * position.volume)) * 100 if entry_price > 0 else 0.0
            
            # Calculate time in position
            open_time = datetime.fromtimestamp(position.time, timezone.utc)
            time_in_position = datetime.now(timezone.utc) - open_time
            
            # Determine position health
            health = self._assess_position_health(unrealized_pnl_pct, time_in_position)
            
            # Make recommendation based on analysis
            recommendation, reasoning, suggested_stop, suggested_tp = self._make_exit_decision(
                position, market_data, unrealized_pnl_pct, time_in_position, health
            )
            
            analysis = PositionAnalysis(
                ticket=ticket,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                time_in_position=time_in_position,
                health=health,
                recommendation=recommendation,
                reasoning=reasoning,
                suggested_stop=suggested_stop,
                suggested_take_profit=suggested_tp,
                confidence=self._calculate_confidence(health, market_data)
            )
            
            # Store in history
            with self._lock:
                self.position_history.append(analysis)
            
            return analysis
            
        except Exception as e:  # noqa: BLE001 - catch any analysis failure
            logger.error(f"Error analyzing position {position.ticket}: {e}")
            return self._default_analysis(position)
    
    def _default_analysis(self, position: Any) -> PositionAnalysis:
        """Return default analysis when real analysis fails"""
        return PositionAnalysis(
            ticket=position.ticket,
            symbol=position.symbol,
            direction="BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL",
            entry_price=position.price_open,
            current_price=position.price_current,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            time_in_position=timedelta(0),
            health=PositionHealth.FAIR,
            recommendation=ExitDecision.HOLD,
            reasoning="Analysis failed - using default hold",
            suggested_stop=None,
            suggested_take_profit=None,
            confidence=0.3
        )
    
    def _assess_position_health(self, pnl_pct: float, time_in_position: timedelta) -> PositionHealth:
        """Assess the health of a position based on PnL and time"""
        # Excellent: Strong profit in reasonable time
        if pnl_pct > 1.0 and time_in_position < timedelta(hours=24):
            return PositionHealth.EXCELLENT
        
        # Good: Profitable or small loss
        if pnl_pct > 0.0:
            return PositionHealth.GOOD
        
        # Fair: Small loss
        if pnl_pct > -0.5:
            return PositionHealth.FAIR
        
        # Poor: Moderate loss
        if pnl_pct > -1.5:
            return PositionHealth.POOR
        
        # Critical: Large loss
        return PositionHealth.CRITICAL
    
    def _make_exit_decision(self, position: Any, market_data: dict[str, Any], 
                           pnl_pct: float, time_in_position: timedelta, 
                           health: PositionHealth) -> tuple[ExitDecision, str, float | None, float | None]:
        """Make intelligent exit decision based on multiple factors"""
        
        # Check for immediate exit conditions
        if health == PositionHealth.CRITICAL:
            return ExitDecision.EXIT_EARLY, "Critical position health - exit recommended", None, None
        
        # Check for trend reversal signals
        if self._signaling_trend_reversal(position, market_data):
            return ExitDecision.EXIT_EARLY, "Trend reversal detected - exit recommended", None, None
        
        # Check for approaching key levels
        proximity_to_level = market_data.get('proximity_to_level', 0.0)
        if proximity_to_level > 0.8:  # Very close to key level
            if pnl_pct > 0.5:  # If profitable
                return ExitDecision.EXIT_EARLY, "Near key resistance/support with profit - take exit", None, None
            else:
                return ExitDecision.TIGHTEN_STOPS, "Near key level - tighten stops", self._calculate_tightened_stop(position, market_data), None
        
        # Check for regime change
        current_regime = market_data.get('market_regime', MarketRegime.UNCERTAIN)
        if current_regime == MarketRegime.VOLATILE and pnl_pct > 0.3:
            return ExitDecision.PARTIAL_EXIT, "High volatility with profit - partial exit recommended", None, None
        
        # Check for momentum divergence
        if self._check_momentum_divergence(position, market_data):
            if pnl_pct > 0.5:
                return ExitDecision.EXIT_EARLY, "Momentum divergence with profit - exit", None, None
            else:
                return ExitDecision.TIGHTEN_STOPS, "Momentum divergence - tighten stops", self._calculate_tightened_stop(position, market_data), None
        
        # Check for breakeven opportunity
        if pnl_pct > 0.8 and time_in_position > timedelta(hours=4):
            return ExitDecision.MOVE_BREAKEVEN, "Strong profit - move to breakeven", position.price_open, None
        
        # Default: hold with suggestions
        suggested_stop = self._calculate_dynamic_stop(position, market_data)
        suggested_tp = self._calculate_dynamic_take_profit(position, market_data)
        
        return ExitDecision.HOLD, "Position performing normally - hold with monitoring", suggested_stop, suggested_tp
    
    def _signaling_trend_reversal(self, position: Any, market_data: dict[str, Any]) -> bool:
        """Check if market is signaling a trend reversal"""
        try:
            # Check ADX trend strength
            adx_value = market_data.get('adx_value', 0)
            if adx_value < 20:  # Weak trend
                return True
            
            # Check MACD crossover
            macd_signal = market_data.get('macd_signal_type', 'neutral')
            if macd_signal in ['bearish_crossover', 'bullish_crossover']:
                # Check if crossover opposes position direction
                position_direction = "bullish" if position.type == mt5.POSITION_TYPE_BUY else "bearish"
                if (macd_signal == 'bearish_crossover' and position_direction == 'bullish') or \
                   (macd_signal == 'bullish_crossover' and position_direction == 'bearish'):
                    return True
            
            return False
            
        except Exception:  # noqa: BLE001 - return False on any error
            return False
    
    def _check_momentum_divergence(self, position: Any, market_data: dict[str, Any]) -> bool:
        """Check for momentum divergence"""
        try:
            # Simple divergence check: price moving one way, momentum another
            rsi = market_data.get('rsi', 50)
            price_momentum = market_data.get('price_momentum', 0)
            
            position_direction = "bullish" if position.type == mt5.POSITION_TYPE_BUY else "bearish"
            
            # Bullish divergence for bearish position
            if position_direction == "bearish" and price_momentum < 0 and rsi > 50:
                return True
            
            # Bearish divergence for bullish position
            if position_direction == "bullish" and price_momentum > 0 and rsi < 50:  # noqa: SIM103
                return True
            
            return False
            
        except Exception:  # noqa: BLE001 - return False on any error
            return False
    
    def _calculate_tightened_stop(self, position: Any, market_data: dict[str, Any]) -> float:
        """Calculate a tightened stop loss"""
        current_price = position.price_current
        atr = market_data.get('atr', current_price * 0.001)
        
        if position.type == mt5.POSITION_TYPE_BUY:
            return current_price - (atr * 0.5)  # Tighter than normal
        else:
            return current_price + (atr * 0.5)
    
    def _calculate_dynamic_stop(self, position: Any, market_data: dict[str, Any]) -> float:
        """Calculate dynamic stop based on market conditions"""
        current_price = position.price_current
        atr = market_data.get('atr', current_price * 0.001)
        
        # Adjust stop based on volatility
        volatility_regime = market_data.get('volatility_regime', 'normal')
        if volatility_regime == 'high':
            atr_multiplier = 2.0  # Wider stops in high volatility
        elif volatility_regime == 'low':
            atr_multiplier = 1.0  # Tighter stops in low volatility
        else:
            atr_multiplier = 1.5  # Normal
        
        if position.type == mt5.POSITION_TYPE_BUY:
            return current_price - (atr * atr_multiplier)
        else:
            return current_price + (atr * atr_multiplier)
    
    def _calculate_dynamic_take_profit(self, position: Any, market_data: dict[str, Any]) -> float:
        """Calculate dynamic take profit based on market conditions"""
        current_price = position.price_current
        atr = market_data.get('atr', current_price * 0.001)
        
        # Use support/resistance levels if available
        resistance_levels = market_data.get('resistance_levels', [])
        support_levels = market_data.get('support_levels', [])
        
        if position.type == mt5.POSITION_TYPE_BUY and resistance_levels:
            # Use nearest resistance as target
            nearest_resistance = min([r for r in resistance_levels if r > current_price], default=None)
            if nearest_resistance:
                return nearest_resistance
        elif position.type == mt5.POSITION_TYPE_SELL and support_levels:
            # Use nearest support as target
            nearest_support = max([s for s in support_levels if s < current_price], default=None)
            if nearest_support:
                return nearest_support
        
        # Fallback to ATR-based target
        if position.type == mt5.POSITION_TYPE_BUY:
            return current_price + (atr * 3.0)
        else:
            return current_price - (atr * 3.0)
    
    def _calculate_confidence(self, health: PositionHealth, market_data: dict[str, Any]) -> float:
        """Calculate confidence in the recommendation"""
        base_confidence = {
            PositionHealth.EXCELLENT: 0.9,
            PositionHealth.GOOD: 0.7,
            PositionHealth.FAIR: 0.5,
            PositionHealth.POOR: 0.6,
            PositionHealth.CRITICAL: 0.8
        }.get(health, 0.5)
        
        # Adjust based on data quality
        data_quality = market_data.get('data_quality', 1.0)
        return base_confidence * data_quality
    
    def analyze_all_positions(self, market_data: dict[str, Any]) -> list[PositionAnalysis]:
        """Analyze all open positions"""
        try:
            ensure_connected()
            positions = get_open_positions(magic=RISK.magic_number)
            
            analyses = []
            for position in positions:
                analysis = self.analyze_position(position, market_data)
                analyses.append(analysis)
            
            return analyses
            
        except Exception as e:  # noqa: BLE001 - catch any analysis failure
            logger.error(f"Error analyzing all positions: {e}")
            return []
    
    def calculate_volatility_adjusted_size(self, symbol: str, base_size: float, 
                                         df: pd.DataFrame) -> VolatilityAdjustment:
        """
        Calculate position size adjusted for current volatility.
        
        Args:
            symbol: Trading symbol
            base_size: Base position size from risk calculation
            df: DataFrame with price data
            
        Returns:
            VolatilityAdjustment with adjusted size and reasoning
        """
        if not ADVANCED_RISK.enable_volatility_adjusted_sizing:
            return VolatilityAdjustment(
                symbol=symbol,
                base_size=base_size,
                adjusted_size=base_size,
                volatility_ratio=1.0,
                adjustment_factor=1.0,
                reason="Volatility adjustment disabled"
            )
        
        try:
            # Calculate current volatility
            returns = df['close'].pct_change().dropna()
            current_volatility = returns.rolling(ADVANCED_RISK.volatility_lookback_period).std().iloc[-1]
            avg_volatility = returns.rolling(ADVANCED_RISK.volatility_lookback_period * 2).std().mean()
            
            if avg_volatility == 0 or pd.isna(current_volatility) or pd.isna(avg_volatility):
                return VolatilityAdjustment(
                    symbol=symbol,
                    base_size=base_size,
                    adjusted_size=base_size,
                    volatility_ratio=1.0,
                    adjustment_factor=1.0,
                    reason="Could not calculate volatility"
                )
            
            volatility_ratio = current_volatility / avg_volatility
            
            # Determine adjustment factor
            if volatility_ratio >= ADVANCED_RISK.volatility_ratio_high:
                adjustment_factor = ADVANCED_RISK.high_volatility_multiplier
                reason = f"High volatility ({volatility_ratio:.2f}x normal) - reducing position size"
            elif volatility_ratio <= ADVANCED_RISK.volatility_ratio_low:
                adjustment_factor = ADVANCED_RISK.low_volatility_multiplier
                reason = f"Low volatility ({volatility_ratio:.2f}x normal) - increasing position size"
            else:
                adjustment_factor = 1.0
                reason = f"Normal volatility ({volatility_ratio:.2f}x normal) - no adjustment"
            
            adjusted_size = base_size * adjustment_factor
            
            return VolatilityAdjustment(
                symbol=symbol,
                base_size=base_size,
                adjusted_size=adjusted_size,
                volatility_ratio=volatility_ratio,
                adjustment_factor=adjustment_factor,
                reason=reason
            )
            
        except Exception as e:  # noqa: BLE001 - catch any calculation failure
            logger.error(f"Error calculating volatility adjustment for {symbol}: {e}")
            return VolatilityAdjustment(
                symbol=symbol,
                base_size=base_size,
                adjusted_size=base_size,
                volatility_ratio=1.0,
                adjustment_factor=1.0,
                reason=f"Error in calculation: {e!s}"
            )
    
    def get_position_summary(self) -> dict[str, Any]:
        """Get summary of all position analyses"""
        with self._lock:
            recent_analyses = list(self.position_history)[-10:]
            
            health_distribution = {}
            for analysis in recent_analyses:
                health = analysis.health.value
                health_distribution[health] = health_distribution.get(health, 0) + 1
            
            recommendation_distribution = {}
            for analysis in recent_analyses:
                rec = analysis.recommendation.value
                recommendation_distribution[rec] = recommendation_distribution.get(rec, 0) + 1
            
            return {
                "total_analyzed": len(self.position_history),
                "recent_analyses": len(recent_analyses),
                "health_distribution": health_distribution,
                "recommendation_distribution": recommendation_distribution,
                "recent_decisions": [
                    {
                        "ticket": ticket,
                        "decision": decision.value,
                        "reason": reason
                    }
                    for ticket, decision, reason in list(self.exit_decisions)[-10:]
                ]
            }