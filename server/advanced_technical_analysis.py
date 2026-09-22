"""
advanced_technical_analysis.py
------------------------------
Advanced technical analysis module providing enhanced indicators for trend analysis,
market regime detection, support/resistance levels, and volume analysis.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd
import pandas_ta as ta
import numpy as np

from config import ADVANCED_ANALYSIS, INDICATORS

logger = logging.getLogger("trading_bot.advanced_technical_analysis")


class MarketRegime(str, Enum):
    """Market regime classification"""
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNCERTAIN = "uncertain"


class TrendStrength(str, Enum):
    """Trend strength classification"""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


@dataclass
class ADXResult:
    """ADX analysis result"""
    adx_value: float
    trend_strength: TrendStrength
    plus_di: float
    minus_di: float
    trend_direction: str  # "bullish", "bearish", or "neutral"


@dataclass
class MACDResult:
    """MACD analysis result"""
    macd: float
    signal: float
    histogram: float
    signal_type: str  # "bullish_crossover", "bearish_crossover", "momentum_up", "momentum_down", "neutral"


@dataclass
class VolumeAnalysis:
    """Volume analysis result"""
    current_volume: float
    average_volume: float
    volume_ratio: float
    surge_detected: bool
    trend_confirmation: str  # "confirmed", "divergence", "neutral"


@dataclass
class SupportResistanceLevels:
    """Support and resistance levels"""
    support_levels: list[float]
    resistance_levels: list[float]
    key_pivot: float
    nearest_support: float | None
    nearest_resistance: float | None
    proximity_to_level: float  # 0.0-1.0, higher means closer to a key level


@dataclass
class MarketRegimeAnalysis:
    """Market regime analysis result"""
    regime: MarketRegime
    volatility: float
    adx_strength: float
    confidence: float
    recommended_approach: str


@dataclass
class TrendMaturityAnalysis:
    """Trend maturity analysis"""
    stage: str  # "early", "mature", "exhausted"
    strength_score: float  # 0.0-1.0
    duration_bars: int
    momentum_score: float
    divergence_detected: bool


def calculate_adx(df: pd.DataFrame, period: int = 14) -> ADXResult:
    """
    Calculate Average Directional Index for trend strength measurement.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ADX calculation period
        
    Returns:
        ADXResult with trend strength and direction information
    """
    if df.empty or len(df) < period * 2:
        logger.warning("Insufficient data for ADX calculation")
        return ADXResult(0.0, TrendStrength.NONE, 0.0, 0.0, "neutral")
    
    try:
        adx_result = ta.adx(df['high'], df['low'], df['close'], length=period)
        
        if adx_result is None or adx_result.empty:
            return ADXResult(0.0, TrendStrength.NONE, 0.0, 0.0, "neutral")
        
        adx = adx_result[f'ADX_{period}'].iloc[-1]
        plus_di = adx_result[f'DMP_{period}'].iloc[-1]
        minus_di = adx_result[f'DMN_{period}'].iloc[-1]
        
        # Classify trend strength
        if pd.isna(adx) or not math.isfinite(adx):
            trend_strength = TrendStrength.NONE
        elif adx >= ADVANCED_ANALYSIS.adx_trend_threshold:
            trend_strength = TrendStrength.STRONG
        elif adx >= 20:
            trend_strength = TrendStrength.MODERATE
        else:
            trend_strength = TrendStrength.WEAK
        
        # Determine trend direction
        if pd.isna(plus_di) or pd.isna(minus_di):
            trend_direction = "neutral"
        elif plus_di > minus_di:
            trend_direction = "bullish"
        elif minus_di > plus_di:
            trend_direction = "bearish"
        else:
            trend_direction = "neutral"
        
        return ADXResult(
            adx_value=float(adx) if math.isfinite(adx) else 0.0,
            trend_strength=trend_strength,
            plus_di=float(plus_di) if math.isfinite(plus_di) else 0.0,
            minus_di=float(minus_di) if math.isfinite(minus_di) else 0.0,
            trend_direction=trend_direction
        )
        
    except Exception as e:
        logger.error(f"Error calculating ADX: {e}")
        return ADXResult(0.0, TrendStrength.NONE, 0.0, 0.0, "neutral")


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult:
    """
    Calculate MACD for momentum and trend confirmation.
    
    Args:
        df: DataFrame with 'close' column
        fast: Fast EMA period
        slow: Slow EMA period
        signal: Signal line period
        
    Returns:
        MACDResult with MACD values and signal interpretation
    """
    if df.empty or len(df) < slow + signal:
        logger.warning("Insufficient data for MACD calculation")
        return MACDResult(0.0, 0.0, 0.0, "neutral")
    
    try:
        macd_result = ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
        
        if macd_result is None or macd_result.empty:
            return MACDResult(0.0, 0.0, 0.0, "neutral")
        
        macd = macd_result[f'MACD_{fast}_{slow}_{signal}'].iloc[-1]
        signal_line = macd_result[f'MACDs_{fast}_{slow}_{signal}'].iloc[-1]
        histogram = macd_result[f'MACDh_{fast}_{slow}_{signal}'].iloc[-1]
        
        # Determine signal type
        if pd.isna(macd) or pd.isna(signal_line) or pd.isna(histogram):
            signal_type = "neutral"
        elif macd > signal_line and histogram > 0:
            # Check for recent crossover
            prev_histogram = macd_result[f'MACDh_{fast}_{slow}_{signal}'].iloc[-2]
            if pd.notna(prev_histogram) and prev_histogram <= 0:
                signal_type = "bullish_crossover"
            else:
                signal_type = "momentum_up"
        elif macd < signal_line and histogram < 0:
            prev_histogram = macd_result[f'MACDh_{fast}_{slow}_{signal}'].iloc[-2]
            if pd.notna(prev_histogram) and prev_histogram >= 0:
                signal_type = "bearish_crossover"
            else:
                signal_type = "momentum_down"
        else:
            signal_type = "neutral"
        
        return MACDResult(
            macd=float(macd) if math.isfinite(macd) else 0.0,
            signal=float(signal_line) if math.isfinite(signal_line) else 0.0,
            histogram=float(histogram) if math.isfinite(histogram) else 0.0,
            signal_type=signal_type
        )
        
    except Exception as e:
        logger.error(f"Error calculating MACD: {e}")
        return MACDResult(0.0, 0.0, 0.0, "neutral")


def analyze_volume(df: pd.DataFrame, threshold: float = 1.5, lookback: int = 20) -> VolumeAnalysis:
    """
    Analyze volume for trend confirmation and surge detection.
    
    Args:
        df: DataFrame with 'volume' column
        threshold: Volume surge threshold multiplier
        lookback: Period for average volume calculation
        
    Returns:
        VolumeAnalysis with volume metrics and trend confirmation
    """
    if df.empty or len(df) < lookback + 1:
        logger.warning("Insufficient data for volume analysis")
        return VolumeAnalysis(0.0, 0.0, 0.0, False, "neutral")
    
    try:
        current_volume = df['volume'].iloc[-1]
        average_volume = df['volume'].rolling(lookback).mean().iloc[-1]
        
        if pd.isna(average_volume) or average_volume == 0:
            volume_ratio = 0.0
        else:
            volume_ratio = current_volume / average_volume
        
        surge_detected = volume_ratio >= threshold
        
        # Trend confirmation analysis
        recent_price_change = df['close'].pct_change(lookback).iloc[-1]
        
        if pd.isna(recent_price_change):
            trend_confirmation = "neutral"
        elif surge_detected:
            if recent_price_change > 0:
                trend_confirmation = "confirmed"
            else:
                trend_confirmation = "divergence"
        else:
            trend_confirmation = "neutral"
        
        return VolumeAnalysis(
            current_volume=float(current_volume) if math.isfinite(current_volume) else 0.0,
            average_volume=float(average_volume) if math.isfinite(average_volume) else 0.0,
            volume_ratio=float(volume_ratio) if math.isfinite(volume_ratio) else 0.0,
            surge_detected=surge_detected,
            trend_confirmation=trend_confirmation
        )
        
    except Exception as e:
        logger.error(f"Error analyzing volume: {e}")
        return VolumeAnalysis(0.0, 0.0, 0.0, False, "neutral")


def detect_market_regime(df: pd.DataFrame) -> MarketRegimeAnalysis:
    """
    Detect current market regime (trending, ranging, or volatile).
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        
    Returns:
        MarketRegimeAnalysis with regime classification and recommendations
    """
    if df.empty or len(df) < 50:
        logger.warning("Insufficient data for regime detection")
        return MarketRegimeAnalysis(
            MarketRegime.UNCERTAIN, 0.0, 0.0, 0.0, "insufficient_data"
        )
    
    try:
        # Calculate volatility
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() if len(returns) > 0 else 0.0
        
        # Calculate ADX for trend strength
        adx_result = calculate_adx(df, ADVANCED_ANALYSIS.adx_period)
        
        # Calculate price range for ranging detection
        recent_high = df['high'].tail(20).max()
        recent_low = df['low'].tail(20).min()
        price_range = (recent_high - recent_low) / df['close'].iloc[-1] if df['close'].iloc[-1] > 0 else 0.0
        
        # Determine regime
        regime = MarketRegime.UNCERTAIN
        confidence = 0.5
        
        if adx_result.adx_value >= ADVANCED_ANALYSIS.regime_adx_threshold:
            regime = MarketRegime.TRENDING
            confidence = min(0.9, 0.5 + (adx_result.adx_value - ADVANCED_ANALYSIS.regime_adx_threshold) / 50.0)
        elif volatility >= ADVANCED_ANALYSIS.regime_volatility_threshold:
            regime = MarketRegime.VOLATILE
            confidence = min(0.8, 0.5 + (volatility - ADVANCED_ANALYSIS.regime_volatility_threshold) / 0.05)
        elif price_range < 0.01:  # Narrow range indicates ranging
            regime = MarketRegime.RANGING
            confidence = 0.7
        
        # Generate recommendation
        if regime == MarketRegime.TRENDING:
            recommended_approach = f"trend_following_{adx_result.trend_direction}"
        elif regime == MarketRegime.VOLATILE:
            recommended_approach = "reduce_position_size_wider_stops"
        elif regime == MarketRegime.RANGING:
            recommended_approach = "mean_reversion_range_trading"
        else:
            recommended_approach = "wait_for_clarity"
        
        return MarketRegimeAnalysis(
            regime=regime,
            volatility=float(volatility) if math.isfinite(volatility) else 0.0,
            adx_strength=float(adx_result.adx_value) if math.isfinite(adx_result.adx_value) else 0.0,
            confidence=float(confidence),
            recommended_approach=recommended_approach
        )
        
    except Exception as e:
        logger.error(f"Error detecting market regime: {e}")
        return MarketRegimeAnalysis(
            MarketRegime.UNCERTAIN, 0.0, 0.0, 0.0, "analysis_error"
        )


def detect_support_resistance(df: pd.DataFrame, lookback: int = 50) -> SupportResistanceLevels:
    """
    Detect key support and resistance levels using pivot analysis.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        lookback: Period for pivot point analysis
        
    Returns:
        SupportResistanceLevels with key price levels
    """
    if df.empty or len(df) < lookback:
        logger.warning("Insufficient data for support/resistance detection")
        return SupportResistanceLevels([], [], 0.0, None, None, 0.0)
    
    try:
        recent_data = df.tail(lookback)
        current_price = df['close'].iloc[-1]
        
        # Find local maxima and minima
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        
        # Simple pivot point detection
        resistance_levels = []
        support_levels = []
        
        # Find resistance levels (local maxima)
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                resistance_levels.append(highs[i])
        
        # Find support levels (local minima)
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                support_levels.append(lows[i])
        
        # Cluster nearby levels
        resistance_levels = _cluster_levels(resistance_levels, clustering_threshold=0.001)
        support_levels = _cluster_levels(support_levels, clustering_threshold=0.001)
        
        # Add psychological levels (round numbers)
        psychological_levels = _find_psychological_levels(current_price, recent_data)
        resistance_levels.extend(psychological_levels['resistance'])
        support_levels.extend(psychological_levels['support'])
        
        # Sort and limit
        resistance_levels = sorted(set(resistance_levels), reverse=True)[:5]
        support_levels = sorted(set(support_levels))[:5]
        
        # Calculate key pivot (central pivot point)
        key_pivot = (recent_data['high'].max() + recent_data['low'].min() + recent_data['close'].iloc[-1]) / 3
        
        # Find nearest levels
        nearest_resistance = min([r for r in resistance_levels if r > current_price], default=None)
        nearest_support = max([s for s in support_levels if s < current_price], default=None)
        
        # Calculate proximity to key level
        distance_to_resistance = (nearest_resistance - current_price) / current_price if nearest_resistance else float('inf')
        distance_to_support = (current_price - nearest_support) / current_price if nearest_support else float('inf')
        min_distance = min(distance_to_resistance, distance_to_support)
        proximity = max(0.0, 1.0 - min_distance * 10) if min_distance != float('inf') else 0.0
        
        return SupportResistanceLevels(
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            key_pivot=float(key_pivot),
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            proximity=float(proximity)
        )
        
    except Exception as e:
        logger.error(f"Error detecting support/resistance: {e}")
        return SupportResistanceLevels([], [], 0.0, None, None, 0.0)


def _cluster_levels(levels: list[float], clustering_threshold: float) -> list[float]:
    """Cluster nearby price levels to avoid duplicates"""
    if not levels:
        return []
    
    sorted_levels = sorted(levels)
    clusters = []
    current_cluster = [sorted_levels[0]]
    
    for level in sorted_levels[1:]:
        if abs(level - current_cluster[0]) / current_cluster[0] <= clustering_threshold:
            current_cluster.append(level)
        else:
            clusters.append(sum(current_cluster) / len(current_cluster))
            current_cluster = [level]
    
    if current_cluster:
        clusters.append(sum(current_cluster) / len(current_cluster))
    
    return clusters


def _find_psychological_levels(current_price: float, df: pd.DataFrame) -> dict[str, list[float]]:
    """Find psychological levels (round numbers)"""
    rounding_base = ADVANCED_ANALYSIS.psychological_level_rounding
    
    # Calculate range of prices
    price_min = df['low'].min()
    price_max = df['high'].max()
    
    # Generate round number levels
    support_levels = []
    resistance_levels = []
    
    # Support levels below current price
    for i in range(1, 4):
        level = math.floor(current_price / rounding_base) * rounding_base - (i * rounding_base)
        if level >= price_min:
            support_levels.append(level)
    
    # Resistance levels above current price
    for i in range(1, 4):
        level = math.ceil(current_price / rounding_base) * rounding_base + (i * rounding_base)
        if level <= price_max:
            resistance_levels.append(level)
    
    return {
        'support': support_levels,
        'resistance': resistance_levels
    }


def analyze_trend_maturity(df_h1: pd.DataFrame, df_h4: pd.DataFrame) -> TrendMaturityAnalysis:
    """
    Analyze trend maturity to determine if trend is early, mature, or exhausted.
    
    Args:
        df_h1: H1 timeframe DataFrame
        df_h4: H4 timeframe DataFrame
        
    Returns:
        TrendMaturityAnalysis with trend stage and strength metrics
    """
    if df_h1.empty or df_h4.empty:
        logger.warning("Insufficient data for trend maturity analysis")
        return TrendMaturityAnalysis("uncertain", 0.0, 0, 0.0, False)
    
    try:
        # Get EMA values
        ema_fast_h1 = df_h1[f'ema_{INDICATORS.ema_fast}'].iloc[-1]
        ema_slow_h1 = df_h1[f'ema_{INDICATORS.ema_slow}'].iloc[-1]
        ema_fast_h4 = df_h4[f'ema_{INDICATORS.ema_fast}'].iloc[-1]
        ema_slow_h4 = df_h4[f'ema_{INDICATORS.ema_slow}'].iloc[-1]
        
        # Determine trend direction
        if ema_fast_h1 > ema_slow_h1 and ema_fast_h4 > ema_slow_h4:
            trend_direction = "bullish"
        elif ema_fast_h1 < ema_slow_h1 and ema_fast_h4 < ema_slow_h4:
            trend_direction = "bearish"
        else:
            return TrendMaturityAnalysis("uncertain", 0.0, 0, 0.0, False)
        
        # Count consecutive bars in trend direction
        duration_bars = 0
        for i in range(len(df_h1) - 1, -1, -1):
            fast = df_h1[f'ema_{INDICATORS.ema_fast}'].iloc[i]
            slow = df_h1[f'ema_{INDICATORS.ema_slow}'].iloc[i]
            
            if (trend_direction == "bullish" and fast > slow) or \
               (trend_direction == "bearish" and fast < slow):
                duration_bars += 1
            else:
                break
        
        # Calculate trend strength based on EMA separation
        ema_separation = abs(ema_fast_h1 - ema_slow_h1) / df_h1['close'].iloc[-1]
        strength_score = min(1.0, ema_separation * 100)  # Normalize to 0-1
        
        # Calculate momentum using RSI
        rsi_current = df_h1['rsi'].iloc[-1]
        rsi_previous = df_h1['rsi'].iloc[-2]
        momentum_score = (rsi_current - 50) / 50 if not pd.isna(rsi_current) else 0.0
        
        # Check for divergence
        price_momentum = df_h1['close'].pct_change(5).iloc[-1]
        rsi_momentum = rsi_current - rsi_previous if not pd.isna(rsi_previous) else 0.0
        
        divergence_detected = False
        if trend_direction == "bullish" and price_momentum > 0 and rsi_momentum < 0:
            divergence_detected = True  # Bearish divergence
        elif trend_direction == "bearish" and price_momentum < 0 and rsi_momentum > 0:
            divergence_detected = True  # Bullish divergence
        
        # Determine trend stage
        if duration_bars < 10:
            stage = "early"
        elif duration_bars < 30:
            stage = "mature"
        else:
            stage = "exhausted"
        
        # Adjust stage based on divergence
        if divergence_detected and stage in ["mature", "exhausted"]:
            stage = "exhausted"  # Divergence in mature trend suggests exhaustion
        
        return TrendMaturityAnalysis(
            stage=stage,
            strength_score=float(strength_score),
            duration_bars=duration_bars,
            momentum_score=float(momentum_score),
            divergence_detected=divergence_detected
        )
        
    except Exception as e:
        logger.error(f"Error analyzing trend maturity: {e}")
        return TrendMaturityAnalysis("uncertain", 0.0, 0, 0.0, False)


def compute_advanced_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all advanced indicators and add them to the DataFrame.
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        DataFrame with advanced indicators added
    """
    if df.empty:
        return df
    
    try:
        df = df.copy()
        
        # Add ADX indicators if enabled
        if ADVANCED_ANALYSIS.use_adx:
            adx_result = ta.adx(df['high'], df['low'], df['close'], length=ADVANCED_ANALYSIS.adx_period)
            if adx_result is not None and not adx_result.empty:
                df[f'adx_{ADVANCED_ANALYSIS.adx_period}'] = adx_result[f'ADX_{ADVANCED_ANALYSIS.adx_period}']
                df[f'plus_di_{ADVANCED_ANALYSIS.adx_period}'] = adx_result[f'DMP_{ADVANCED_ANALYSIS.adx_period}']
                df[f'minus_di_{ADVANCED_ANALYSIS.adx_period}'] = adx_result[f'DMN_{ADVANCED_ANALYSIS.adx_period}']
        
        # Add MACD indicators if enabled
        if ADVANCED_ANALYSIS.use_macd:
            macd_result = ta.macd(df['close'], 
                                fast=ADVANCED_ANALYSIS.macd_fast, 
                                slow=ADVANCED_ANALYSIS.macd_slow, 
                                signal=ADVANCED_ANALYSIS.macd_signal)
            if macd_result is not None and not macd_result.empty:
                df['macd'] = macd_result[f'MACD_{ADVANCED_ANALYSIS.macd_fast}_{ADVANCED_ANALYSIS.macd_slow}_{ADVANCED_ANALYSIS.macd_signal}']
                df['macd_signal'] = macd_result[f'MACDs_{ADVANCED_ANALYSIS.macd_fast}_{ADVANCED_ANALYSIS.macd_slow}_{ADVANCED_ANALYSIS.macd_signal}']
                df['macd_histogram'] = macd_result[f'MACDh_{ADVANCED_ANALYSIS.macd_fast}_{ADVANCED_ANALYSIS.macd_slow}_{ADVANCED_ANALYSIS.macd_signal}']
        
        # Add volume moving average if enabled
        if ADVANCED_ANALYSIS.use_volume_confirmation:
            df[f'volume_ma_{ADVANCED_ANALYSIS.volume_lookback_period}'] = \
                df['volume'].rolling(ADVANCED_ANALYSIS.volume_lookback_period).mean()
        
        return df.dropna()
        
    except Exception as e:
        logger.error(f"Error computing advanced indicators: {e}")
        return df