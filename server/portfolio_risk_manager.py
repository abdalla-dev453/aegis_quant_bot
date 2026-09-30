"""
portfolio_risk_manager.py
--------------------------
Portfolio-level risk management system for analyzing overall exposure,
correlation risks, and concentration across multiple positions.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pandas as pd
from config import ADVANCED_RISK, RISK, SYMBOL_CORRELATIONS
from data_provider import ensure_connected, get_account_equity, get_open_positions, mt5

logger = logging.getLogger("trading_bot.portfolio_risk_manager")


class PortfolioHealth(str, Enum):
    """Overall portfolio health status"""
    HEALTHY = "healthy"
    CAUTION = "caution"
    DANGER = "danger"
    CRITICAL = "critical"


class RiskType(str, Enum):
    """Types of portfolio risks"""
    CORRELATION = "correlation"
    CONCENTRATION = "concentration"
    EXPOSURE = "exposure"
    VOLATILITY = "volatility"


@dataclass
class RiskAlert:
    """Alert for a specific risk type"""
    risk_type: RiskType
    severity: str  # "low", "medium", "high", "critical"
    message: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    recommended_action: str


@dataclass
class CurrencyExposure:
    """Exposure analysis for a specific currency"""
    currency: str
    total_exposure_usd: float
    exposure_percentage: float
    positions_count: int
    net_direction: str  # "long", "short", "neutral"


@dataclass
class PortfolioAnalysis:
    """Complete portfolio risk analysis"""
    overall_health: PortfolioHealth
    total_exposure_usd: float
    exposure_percentage: float
    equity: float = 0.0
    currency_exposures: list[CurrencyExposure] = ()
    correlation_risk_score: float = 0.0
    concentration_risk_score: float = 0.0
    volatility_risk_score: float = 0.0
    alerts: list[RiskAlert] = ()
    risk_summary: str = ""
    recommended_actions: list[str] = ()
    timestamp: datetime | None = None


class PortfolioRiskManager:
    """
    Advanced portfolio-level risk management with correlation analysis,
    concentration monitoring, and exposure tracking.
    """
    
    def __init__(self):
        self.analysis_history: list[PortfolioAnalysis] = []
        self.alert_history: list[RiskAlert] = []
        self._lock = threading.Lock()
        
        logger.info("Portfolio risk manager initialized")
    
    def analyze_portfolio(self) -> PortfolioAnalysis:
        """
        Perform comprehensive portfolio risk analysis.
        
        Returns:
            PortfolioAnalysis with complete risk assessment
        """
        try:
            ensure_connected()
            positions = get_open_positions(magic=RISK.magic_number)
            
            if not positions:
                return self._empty_portfolio_analysis()
            
            # Get account equity for exposure calculations
            equity = get_account_equity()
            
            # Calculate total exposure
            total_exposure_usd = self._calculate_total_exposure(positions)
            exposure_percentage = (total_exposure_usd / equity) * 100 if equity > 0 else 0.0
            
            # Analyze currency exposures
            currency_exposures = self._analyze_currency_exposures(positions, equity)
            
            # Calculate correlation risk
            correlation_risk = self._calculate_correlation_risk(positions)
            
            # Calculate concentration risk
            concentration_risk = self._calculate_concentration_risk(positions, currency_exposures)
            
            # Calculate volatility risk
            volatility_risk = self._calculate_volatility_risk(positions)
            
            # Generate alerts
            alerts = self._generate_risk_alerts(
                exposure_percentage, correlation_risk, concentration_risk, volatility_risk
            )
            
            # Determine overall health
            overall_health = self._determine_portfolio_health(
                exposure_percentage, correlation_risk, concentration_risk, volatility_risk, alerts
            )
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                overall_health, exposure_percentage, correlation_risk, concentration_risk
            )
            
            # Create summary
            risk_summary = self._generate_risk_summary(
                overall_health, exposure_percentage, correlation_risk, concentration_risk
            )
            
            analysis = PortfolioAnalysis(
                overall_health=overall_health,
                total_exposure_usd=total_exposure_usd,
                exposure_percentage=exposure_percentage,
                equity=equity,
                currency_exposures=currency_exposures,
                correlation_risk_score=correlation_risk,
                concentration_risk_score=concentration_risk,
                volatility_risk_score=volatility_risk,
                alerts=alerts,
                risk_summary=risk_summary,
                recommended_actions=recommendations,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Store in history
            with self._lock:
                self.analysis_history.append(analysis)
                self.alert_history.extend(alerts)
                # Keep only recent history
                if len(self.analysis_history) > 50:
                    self.analysis_history = self.analysis_history[-50:]
                if len(self.alert_history) > 100:
                    self.alert_history = self.alert_history[-100:]
            
            return analysis
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error analyzing portfolio: {e}")
            return self._empty_portfolio_analysis()
    
    def _empty_portfolio_analysis(self) -> PortfolioAnalysis:
        """Return empty analysis when no positions exist"""
        return PortfolioAnalysis(
            overall_health=PortfolioHealth.HEALTHY,
            total_exposure_usd=0.0,
            exposure_percentage=0.0,
            equity=0.0,
            currency_exposures=[],
            correlation_risk_score=0.0,
            concentration_risk_score=0.0,
            volatility_risk_score=0.0,
            alerts=[],
            risk_summary="No open positions",
            recommended_actions=[],
            timestamp=datetime.now(timezone.utc)
        )
    
    def _calculate_total_exposure(self, positions: list) -> float:
        """Calculate total portfolio exposure in USD"""
        total_exposure = 0.0
        
        for position in positions:
            try:
                # Get contract size and current price
                symbol_info = mt5.symbol_info(position.symbol)
                if symbol_info is None:
                    continue
                
                contract_size = symbol_info.trade_contract_size
                current_price = position.price_current
                
                # Calculate position value in USD
                position_value = position.volume * contract_size * current_price
                total_exposure += position_value
                
            except Exception as e:  # noqa: BLE001 - catch any failure
                logger.debug(f"Error calculating exposure for {position.symbol}: {e}")
                continue
        
        return total_exposure
    
    def _analyze_currency_exposures(self, positions: list, equity: float) -> list[CurrencyExposure]:
        """Analyze exposure by currency"""
        currency_data = defaultdict(lambda: {
            'total_exposure': 0.0,
            'positions': [],
            'long_volume': 0.0,
            'short_volume': 0.0
        })
        
        for position in positions:
            try:
                # Extract currency from symbol (e.g., EURUSD -> USD, EUR)
                currency = self._extract_base_currency(position.symbol)
                
                # Calculate position value
                symbol_info = mt5.symbol_info(position.symbol)
                if symbol_info is None:
                    continue
                
                contract_size = symbol_info.trade_contract_size
                current_price = position.price_current
                position_value = position.volume * contract_size * current_price
                
                currency_data[currency]['total_exposure'] += position_value
                currency_data[currency]['positions'].append(position.ticket)
                
                if position.type == mt5.POSITION_TYPE_BUY:
                    currency_data[currency]['long_volume'] += position.volume
                else:
                    currency_data[currency]['short_volume'] += position.volume
                    
            except Exception as e:  # noqa: BLE001 - catch any failure
                logger.debug(f"Error analyzing currency exposure for {position.symbol}: {e}")
                continue
        
        # Convert to CurrencyExposure objects
        exposures = []

        for currency, data in currency_data.items():
            exposure_percentage = (data['total_exposure'] / equity) * 100 if equity > 0 else 0.0
            
            # Determine net direction
            if data['long_volume'] > data['short_volume']:
                net_direction = "long"
            elif data['short_volume'] > data['long_volume']:
                net_direction = "short"
            else:
                net_direction = "neutral"
            
            exposures.append(CurrencyExposure(
                currency=currency,
                total_exposure_usd=data['total_exposure'],
                exposure_percentage=exposure_percentage,
                positions_count=len(data['positions']),
                net_direction=net_direction
            ))
        
        return sorted(exposures, key=lambda x: x.exposure_percentage, reverse=True)
    
    def _extract_base_currency(self, symbol: str) -> str:
        """Extract base currency from symbol"""
        # Simple extraction - assumes standard forex naming
        if len(symbol) >= 6:
            return symbol[:3]
        return symbol
    
    def _calculate_correlation_risk(self, positions: list) -> float:
        """Calculate correlation risk score (0.0-1.0)"""
        if len(positions) < 2:
            return 0.0
        
        correlation_risk = 0.0
        analyzed_pairs = set()
        
        for i, pos1 in enumerate(positions):
            for j, pos2 in enumerate(positions):
                if i >= j:
                    continue
                
                # Check if positions are in same direction
                same_direction = (
                    (pos1.type == mt5.POSITION_TYPE_BUY and pos2.type == mt5.POSITION_TYPE_BUY) or
                    (pos1.type == mt5.POSITION_TYPE_SELL and pos2.type == mt5.POSITION_TYPE_SELL)
                )
                
                if not same_direction:
                    continue
                
                # Get correlation for the pair
                pair = tuple(sorted((pos1.symbol, pos2.symbol)))
                if pair in analyzed_pairs:
                    continue
                
                correlation = SYMBOL_CORRELATIONS.get(pair, 0.0)
                
                if correlation >= RISK.correlation_threshold:
                    # High correlation in same direction adds to risk
                    correlation_risk += correlation
                    analyzed_pairs.add(pair)
        
        # Normalize to 0-1 range
        max_possible_risk = len(positions) * 1.0  # Maximum possible correlation
        return min(1.0, correlation_risk / max_possible_risk) if max_possible_risk > 0 else 0.0
    
    def _calculate_concentration_risk(self, positions: list, 
                                    currency_exposures: list[CurrencyExposure]) -> float:
        """Calculate concentration risk score (0.0-1.0)"""
        if not currency_exposures:
            return 0.0
        
        # Calculate Herfindahl-Hirschman Index (HHI) for concentration
        total_exposure = sum(exp.exposure_percentage for exp in currency_exposures)
        if total_exposure == 0:
            return 0.0
        
        hhi = sum((exp.exposure_percentage / total_exposure) ** 2 for exp in currency_exposures)
        
        # Normalize HHI to 0-1 range (HHI ranges from 1/n to 1.0)
        min_hhi = 1.0 / len(currency_exposures) if currency_exposures else 1.0
        normalized_hhi = (hhi - min_hhi) / (1.0 - min_hhi) if min_hhi < 1.0 else 0.0
        
        return normalized_hhi
    
    def _calculate_volatility_risk(self, positions: list) -> float:
        """Calculate volatility risk score (0.0-1.0)"""
        if not positions:
            return 0.0
        
        volatility_scores = []
        
        for position in positions:
            try:
                # Get recent price data for volatility calculation
                rates = mt5.copy_rates_from_pos(position.symbol, mt5.TIMEFRAME_H1, 0, 50)
                if rates is None or len(rates) < 20:
                    continue
                
                df = pd.DataFrame(rates)
                returns = df['close'].pct_change().dropna()
                
                if len(returns) < 10:
                    continue
                
                # Calculate volatility
                volatility = returns.std()
                
                # Normalize to score (assuming 2% daily vol is high)
                vol_score = min(1.0, volatility / 0.02)
                volatility_scores.append(vol_score)
                
            except Exception as e:  # noqa: BLE001 - catch any failure
                logger.debug(f"Error calculating volatility for {position.symbol}: {e}")
                continue
        
        if not volatility_scores:
            return 0.0
        
        # Return average volatility score
        return sum(volatility_scores) / len(volatility_scores)
    
    def _generate_risk_alerts(self, exposure_pct: float, correlation_risk: float,
                             concentration_risk: float, volatility_risk: float) -> list[RiskAlert]:
        """Generate risk alerts based on thresholds"""
        alerts = []
        now = datetime.now(timezone.utc)
        
        # Exposure alerts
        if exposure_pct >= ADVANCED_RISK.max_portfolio_exposure_pct:
            alerts.append(RiskAlert(
                risk_type=RiskType.EXPOSURE,
                severity="critical",
                message=f"Portfolio exposure ({exposure_pct:.1f}%) exceeds maximum ({ADVANCED_RISK.max_portfolio_exposure_pct:.1f}%)",
                current_value=exposure_pct,
                threshold_value=ADVANCED_RISK.max_portfolio_exposure_pct,
                timestamp=now,
                recommended_action="Reduce position sizes or close some positions"
            ))
        elif exposure_pct >= ADVANCED_RISK.max_portfolio_exposure_pct * 0.8:
            alerts.append(RiskAlert(
                risk_type=RiskType.EXPOSURE,
                severity="high",
                message=f"Portfolio exposure ({exposure_pct:.1f}%) approaching maximum",
                current_value=exposure_pct,
                threshold_value=ADVANCED_RISK.max_portfolio_exposure_pct,
                timestamp=now,
                recommended_action="Monitor closely, consider reducing exposure"
            ))
        
        # Correlation alerts
        if correlation_risk >= 0.7:
            alerts.append(RiskAlert(
                risk_type=RiskType.CORRELATION,
                severity="high",
                message=f"High correlation risk detected ({correlation_risk:.2f})",
                current_value=correlation_risk,
                threshold_value=0.7,
                timestamp=now,
                recommended_action="Consider reducing correlated positions or hedging"
            ))
        elif correlation_risk >= 0.5:
            alerts.append(RiskAlert(
                risk_type=RiskType.CORRELATION,
                severity="medium",
                message=f"Moderate correlation risk ({correlation_risk:.2f})",
                current_value=correlation_risk,
                threshold_value=0.5,
                timestamp=now,
                recommended_action="Monitor correlation exposure"
            ))
        
        # Concentration alerts
        if concentration_risk >= 0.7:
            alerts.append(RiskAlert(
                risk_type=RiskType.CONCENTRATION,
                severity="high",
                message=f"High concentration risk ({concentration_risk:.2f})",
                current_value=concentration_risk,
                threshold_value=0.7,
                timestamp=now,
                recommended_action="Diversify across more currencies/instruments"
            ))
        elif concentration_risk >= 0.5:
            alerts.append(RiskAlert(
                risk_type=RiskType.CONCENTRATION,
                severity="medium",
                message=f"Moderate concentration risk ({concentration_risk:.2f})",
                current_value=concentration_risk,
                threshold_value=0.5,
                timestamp=now,
                recommended_action="Consider diversification"
            ))
        
        # Volatility alerts
        if volatility_risk >= 0.8:
            alerts.append(RiskAlert(
                risk_type=RiskType.VOLATILITY,
                severity="high",
                message=f"High volatility risk ({volatility_risk:.2f})",
                current_value=volatility_risk,
                threshold_value=0.8,
                timestamp=now,
                recommended_action="Reduce position sizes, widen stops"
            ))
        
        return alerts
    
    def _determine_portfolio_health(self, exposure_pct: float, correlation_risk: float,
                                  concentration_risk: float, volatility_risk: float,
                                  alerts: list[RiskAlert]) -> PortfolioHealth:
        """Determine overall portfolio health status"""
        # Check for critical alerts
        critical_alerts = [a for a in alerts if a.severity == "critical"]
        if critical_alerts:
            return PortfolioHealth.CRITICAL
        
        # Check for high severity alerts
        high_alerts = [a for a in alerts if a.severity == "high"]
        if len(high_alerts) >= 2:
            return PortfolioHealth.DANGER
        elif high_alerts:
            return PortfolioHealth.CAUTION
        
        # Check overall risk levels
        if (exposure_pct > ADVANCED_RISK.max_portfolio_exposure_pct * 0.9 or
            correlation_risk > 0.6 or
            concentration_risk > 0.6 or
            volatility_risk > 0.7):
            return PortfolioHealth.CAUTION
        
        return PortfolioHealth.HEALTHY
    
    def _generate_recommendations(self, health: PortfolioHealth, exposure_pct: float,
                                 correlation_risk: float, concentration_risk: float) -> list[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        if health == PortfolioHealth.CRITICAL:
            recommendations.append("IMMEDIATE ACTION REQUIRED: Reduce portfolio exposure")
            recommendations.append("Close largest positions or reduce position sizes")
        elif health == PortfolioHealth.DANGER:
            recommendations.append("Reduce portfolio exposure within next trading session")
            recommendations.append("Consider closing correlated positions")
        elif health == PortfolioHealth.CAUTION:
            if exposure_pct > ADVANCED_RISK.max_portfolio_exposure_pct * 0.8:
                recommendations.append("Consider reducing overall exposure")
            if correlation_risk > 0.5:
                recommendations.append("Review and reduce correlated positions")
            if concentration_risk > 0.5:
                recommendations.append("Diversify across more instruments")
        else:
            recommendations.append("Portfolio risk levels are acceptable")
            recommendations.append("Continue monitoring")
        
        return recommendations
    
    def _generate_risk_summary(self, health: PortfolioHealth, exposure_pct: float,
                            correlation_risk: float, concentration_risk: float) -> str:
        """Generate human-readable risk summary"""
        health_desc = {
            PortfolioHealth.HEALTHY: "Portfolio risk levels are within acceptable limits",
            PortfolioHealth.CAUTION: "Portfolio risk levels require attention",
            PortfolioHealth.DANGER: "Portfolio risk levels are elevated",
            PortfolioHealth.CRITICAL: "Portfolio risk levels are critical"
        }.get(health, "Unknown health status")
        
        details = f"Exposure: {exposure_pct:.1f}%, Correlation Risk: {correlation_risk:.2f}, Concentration: {concentration_risk:.2f}"
        
        return f"{health_desc}. {details}"
    
    def check_pre_trade_risk(self, symbol: str, direction: str, 
                           volume: float) -> tuple[bool, str]:
        """
        Check if a new trade would violate portfolio risk limits.
        
        Args:
            symbol: Symbol to trade
            direction: Trade direction ("BUY" or "SELL")
            volume: Position size
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        if not ADVANCED_RISK.enable_portfolio_risk:
            return True, "Portfolio risk controls disabled"
        
        try:
            # Get current portfolio analysis
            current_analysis = self.analyze_portfolio()
            
            equity = current_analysis.equity or get_account_equity()
            
            # Calculate new position exposure
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False, f"Cannot get symbol info for {symbol}"
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False, f"Cannot get tick for {symbol}"
            current_price = tick.ask if direction == "BUY" else tick.bid
            position_value = volume * symbol_info.trade_contract_size * current_price
            
            # Check if new trade would exceed exposure limit
            new_exposure = current_analysis.total_exposure_usd + position_value
            equity = get_account_equity()
            new_exposure_pct = (new_exposure / equity) * 100 if equity > 0 else 0.0
            
            if new_exposure_pct > ADVANCED_RISK.max_portfolio_exposure_pct:
                return False, f"Trade would exceed portfolio exposure limit ({new_exposure_pct:.1f}% > {ADVANCED_RISK.max_portfolio_exposure_pct:.1f}%)"
            
            # Check correlation risk
            if current_analysis.correlation_risk_score > 0.5:
                # Check if new position is correlated with existing ones
                for exp in current_analysis.currency_exposures:
                    if (exp.currency in symbol and 
                        exp.net_direction == direction.lower() and
                        new_exposure_pct > ADVANCED_RISK.max_correlation_exposure_pct):
                        return False, "Trade would exceed correlation exposure limit"
            
            # Check concentration risk
            base_currency = self._extract_base_currency(symbol)
            for exp in current_analysis.currency_exposures:
                if exp.currency == base_currency:
                    new_currency_exposure = exp.exposure_percentage + (position_value / equity) * 100
                    if new_currency_exposure > ADVANCED_RISK.max_currency_concentration_pct:
                        return False, "Trade would exceed currency concentration limit"
            
            return True, "Trade within portfolio risk limits"
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error checking pre-trade risk: {e}")
            return False, f"Error in risk check, blocking trade: {e}"
    
    def get_risk_summary(self) -> dict[str, Any]:
        """Get current portfolio risk summary"""
        try:
            analysis = self.analyze_portfolio()
            
            return {
                "overall_health": analysis.overall_health.value,
                "total_exposure_usd": analysis.total_exposure_usd,
                "exposure_percentage": analysis.exposure_percentage,
                "correlation_risk_score": analysis.correlation_risk_score,
                "concentration_risk_score": analysis.concentration_risk_score,
                "volatility_risk_score": analysis.volatility_risk_score,
                "currency_exposures": [
                    {
                        "currency": exp.currency,
                        "exposure_usd": exp.total_exposure_usd,
                        "exposure_percentage": exp.exposure_percentage,
                        "positions_count": exp.positions_count,
                        "net_direction": exp.net_direction
                    }
                    for exp in analysis.currency_exposures
                ],
                "alerts": [
                    {
                        "type": alert.risk_type.value,
                        "severity": alert.severity,
                        "message": alert.message,
                        "recommended_action": alert.recommended_action,
                        "timestamp": alert.timestamp.isoformat()
                    }
                    for alert in analysis.alerts
                ],
                "recommended_actions": analysis.recommended_actions,
                "risk_summary": analysis.risk_summary,
                "enabled": ADVANCED_RISK.enable_portfolio_risk
            }
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error getting risk summary: {e}")
            return {
                "error": str(e),
                "overall_health": "unknown"
            }


portfolio_risk_manager = PortfolioRiskManager()