"""
prediction_engine.py
--------------------
Advanced prediction engine for price movement forecasting, pattern recognition,
and volatility prediction using machine learning and statistical methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("trading_bot.prediction_engine")

# Optional ML dependencies
try:
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("ML dependencies not available, using fallback predictions")

from advanced_technical_analysis import detect_support_resistance
from config import ADVANCED_ANALYSIS, INDICATORS, PREDICTION


class PredictionDirection(str, Enum):
    """Price movement direction prediction"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


class PredictionConfidence(str, Enum):
    """Confidence level for predictions"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class PricePrediction:
    """Price movement prediction result"""
    direction: PredictionDirection
    confidence: float  # 0.0-1.0
    confidence_level: PredictionConfidence
    target_price: float | None
    time_horizon: str  # e.g., "5 bars", "1 hour"
    support_levels: list[float]
    resistance_levels: list[float]
    expected_move_pct: float
    reasoning: str
    timestamp: str


@dataclass
class PatternMatch:
    """Chart pattern detection result"""
    pattern_name: str
    confidence: float  # 0.0-1.0
    direction: PredictionDirection
    target_price: float | None
    stop_loss_level: float | None
    completion_pct: float  # 0.0-1.0
    timeframe: str


@dataclass
class VolatilityForecast:
    """Volatility prediction result"""
    expected_volatility: float
    volatility_regime: str  # "low", "normal", "high"
    forecast_horizon: str
    breakout_probability: float
    expected_range: tuple[float, float]
    confidence: float


class PricePredictionEngine:
    """
    Advanced price prediction engine using machine learning and technical analysis.
    Combines multiple prediction methods for robust forecasting.
    """
    
    def __init__(self):
        self.model = None
        self.scaler = None
        self.model_path = Path(__file__).parent / "models" / "price_predictor.pkl"
        self.scaler_path = Path(__file__).parent / "models" / "price_scaler.pkl"
        self.ml_enabled = ML_AVAILABLE and PREDICTION.enable_price_prediction
        
        if self.ml_enabled:
            self.scaler = StandardScaler()
            self._load_or_initialize_model()
        else:
            logger.info("ML prediction disabled, using technical analysis fallback")
    
    def _load_or_initialize_model(self):
        """Load existing model or initialize a new one"""
        if not ML_AVAILABLE:
            return
            
        try:
            if self.model_path.exists() and self.scaler_path.exists():
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                logger.info("Loaded existing prediction model")
            else:
                self._initialize_model()
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.warning(f"Could not load model, initializing new one: {e}")
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize a new prediction model"""
        if not ML_AVAILABLE:
            return
            
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            random_state=42
        )
        logger.info("Initialized new prediction model")
    
    def _extract_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract features for machine learning prediction"""
        if df.empty or len(df) < 50:
            return np.array([])
        
        features = []
        
        # Price momentum features
        for period in [5, 10, 20]:
            returns = df['close'].pct_change(period)
            features.append(returns.iloc[-1] if len(returns) > 0 else 0)
        
        # Volatility features
        for period in [5, 10, 20]:
            volatility = df['close'].pct_change().rolling(period).std()
            features.append(volatility.iloc[-1] if len(volatility) > 0 else 0)
        
        # Technical indicator features
        if f'ema_{INDICATORS.ema_fast}' in df.columns:
            ema_fast = df[f'ema_{INDICATORS.ema_fast}'].iloc[-1]
            ema_slow = df[f'ema_{INDICATORS.ema_slow}'].iloc[-1]
            features.append((ema_fast - ema_slow) / df['close'].iloc[-1])
        
        if 'rsi' in df.columns:
            features.append((df['rsi'].iloc[-1] - 50) / 50)
        
        if 'atr' in df.columns:
            features.append(df['atr'].iloc[-1] / df['close'].iloc[-1])
        
        # Volume features
        if 'volume' in df.columns:
            volume_ma = df['volume'].rolling(20).mean()
            features.append(df['volume'].iloc[-1] / volume_ma.iloc[-1] if len(volume_ma) > 0 else 0)
        
        # Advanced features if available
        if ADVANCED_ANALYSIS.use_adx and f'adx_{ADVANCED_ANALYSIS.adx_period}' in df.columns:
            features.append(df[f'adx_{ADVANCED_ANALYSIS.adx_period}'].iloc[-1] / 100)
        
        if ADVANCED_ANALYSIS.use_macd and 'macd' in df.columns:
            features.append(df['macd'].iloc[-1] / df['close'].iloc[-1])
        
        return np.array(features).reshape(1, -1)
    
    def _prepare_training_data(self, df: pd.DataFrame, lookahead_bars: int = 5) -> tuple:
        """Prepare training data for the model"""
        if len(df) < lookahead_bars + 50:
            return None, None, None
        
        features_list = []
        targets = []
        
        for i in range(50, len(df) - lookahead_bars):
            window = df.iloc[i-50:i]
            features = self._extract_features(window)
            
            if features.size > 0:
                features_list.append(features[0])
                
                # Determine target: did price go up or down?
                future_price = df['close'].iloc[i + lookahead_bars]
                current_price = df['close'].iloc[i]
                
                if future_price > current_price * 1.002:  # 0.2% threshold
                    targets.append(1)  # Up
                elif future_price < current_price * 0.998:  # -0.2% threshold
                    targets.append(0)  # Down
                else:
                    targets.append(2)  # Sideways
        
        if not features_list:
            return None, None, None
        
        X = np.array(features_list)
        y = np.array(targets)
        
        return X, y, df
    
    def train_model(self, df: pd.DataFrame, lookahead_bars: int = 5) -> bool:
        """Train the prediction model with historical data"""
        if not self.ml_enabled:
            logger.info("ML training disabled")
            return False
            
        try:
            X, y, _ = self._prepare_training_data(df, lookahead_bars)
            if X is None or len(X) < 100:
                logger.warning("Insufficient data for training")
                return False
            class_counts = __import__("collections").Counter(y)
            if len(class_counts) < 2 or min(class_counts.values()) < 5:
                logger.warning("Refusing ML training: each class needs at least 5 samples (%s)", class_counts)
                return False
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train model
            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)

            logger.info(f"Model trained - Train score: {train_score:.3f}, Test score: {test_score:.3f}")

            # Save model
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)

            return True

        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error training model: {e}")
            return False

    def predict_price_move(self, df: pd.DataFrame, lookahead_bars: int = 5) -> PricePrediction:
        """
        Predict likely price direction and magnitude.

        Args:
            df: DataFrame with OHLCV and indicator data
            lookahead_bars: Number of bars to predict ahead

        Returns:
            PricePrediction with direction, confidence, and targets
        """
        if df.empty or len(df) < 50:
            return PricePrediction(
                direction=PredictionDirection.SIDEWAYS,
                confidence=0.0,
                confidence_level=PredictionConfidence.LOW,
                target_price=None,
                time_horizon=f"{lookahead_bars} bars",
                support_levels=[],
                resistance_levels=[],
                expected_move_pct=0.0,
                reasoning="Insufficient data for prediction",
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        
        # If ML is not enabled, use fallback prediction
        if not self.ml_enabled:
            return self._fallback_prediction(df, lookahead_bars)
        
        try:
            current_price = df['close'].iloc[-1]
            
            # Extract features and predict
            features = self._extract_features(df)
            if features.size == 0:
                return self._fallback_prediction(df, lookahead_bars)
            
            try:
                features_scaled = self.scaler.transform(features)
                prediction_proba = self.model.predict_proba(features_scaled)[0]
            except Exception:  # noqa: BLE001 - catch any failure
                # Model not trained yet, use fallback
                return self._fallback_prediction(df, lookahead_bars)
            
            # Get prediction
            prediction = self.model.predict(features_scaled)[0]
            
            # Map prediction to direction
            if prediction == 1:
                direction = PredictionDirection.UP
            elif prediction == 0:
                direction = PredictionDirection.DOWN
            else:
                direction = PredictionDirection.SIDEWAYS
            
            # Calculate confidence
            confidence = max(prediction_proba)
            if confidence >= 0.7:
                confidence_level = PredictionConfidence.HIGH
            elif confidence >= 0.5:
                confidence_level = PredictionConfidence.MEDIUM
            else:
                confidence_level = PredictionConfidence.LOW
            
            # Calculate target price based on ATR
            atr = df['atr'].iloc[-1] if 'atr' in df.columns else current_price * 0.001
            expected_move = atr * lookahead_bars * 0.5
            
            if direction == PredictionDirection.UP:
                target_price = current_price + expected_move
            elif direction == PredictionDirection.DOWN:
                target_price = current_price - expected_move
            else:
                target_price = current_price
            
            # Get support/resistance levels
            sr_levels = detect_support_resistance(df.tail(ADVANCED_ANALYSIS.pivot_lookback_period))
            
            # Calculate expected move percentage
            expected_move_pct = abs(expected_move / current_price) * 100
            
            # Generate reasoning
            reasoning = self._generate_reasoning(df, direction, confidence, prediction_proba)
            
            return PricePrediction(
                direction=direction,
                confidence=float(confidence),
                confidence_level=confidence_level,
                target_price=float(target_price) if target_price else None,
                time_horizon=f"{lookahead_bars} bars",
                support_levels=sr_levels.support_levels,
                resistance_levels=sr_levels.resistance_levels,
                expected_move_pct=float(expected_move_pct),
                reasoning=reasoning,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error predicting price move: {e}")
            return self._fallback_prediction(df, lookahead_bars)
    
    def _fallback_prediction(self, df: pd.DataFrame, lookahead_bars: int) -> PricePrediction:
        """Fallback prediction using simple technical analysis"""
        current_price = df['close'].iloc[-1]
        
        # Simple trend-based prediction
        if f'ema_{INDICATORS.ema_fast}' in df.columns and f'ema_{INDICATORS.ema_slow}' in df.columns:
            ema_fast = df[f'ema_{INDICATORS.ema_fast}'].iloc[-1]
            ema_slow = df[f'ema_{INDICATORS.ema_slow}'].iloc[-1]
            
            if ema_fast > ema_slow:
                direction = PredictionDirection.UP
                confidence = 0.6
            elif ema_fast < ema_slow:
                direction = PredictionDirection.DOWN
                confidence = 0.6
            else:
                direction = PredictionDirection.SIDEWAYS
                confidence = 0.4
        else:
            direction = PredictionDirection.SIDEWAYS
            confidence = 0.3
        
        atr = df['atr'].iloc[-1] if 'atr' in df.columns else current_price * 0.001
        expected_move = atr * lookahead_bars * 0.3
        
        if direction == PredictionDirection.UP:
            target_price = current_price + expected_move
        elif direction == PredictionDirection.DOWN:
            target_price = current_price - expected_move
        else:
            target_price = current_price
        
        sr_levels = detect_support_resistance(df.tail(min(50, len(df))))
        
        return PricePrediction(
            direction=direction,
            confidence=confidence,
            confidence_level=PredictionConfidence.MEDIUM if confidence >= 0.5 else PredictionConfidence.LOW,
            target_price=float(target_price) if target_price else None,
            time_horizon=f"{lookahead_bars} bars",
            support_levels=sr_levels.support_levels,
            resistance_levels=sr_levels.resistance_levels,
            expected_move_pct=float(abs(expected_move / current_price) * 100),
            reasoning="Fallback prediction using basic trend analysis",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    def _generate_reasoning(self, df: pd.DataFrame, direction: PredictionDirection, 
                          confidence: float, prediction_proba: np.ndarray) -> str:
        """Generate human-readable reasoning for the prediction"""
        reasons = []
        
        # Add technical analysis context
        if f'ema_{INDICATORS.ema_fast}' in df.columns:
            ema_fast = df[f'ema_{INDICATORS.ema_fast}'].iloc[-1]
            ema_slow = df[f'ema_{INDICATORS.ema_slow}'].iloc[-1]
            if ema_fast > ema_slow:
                reasons.append("EMA bullish alignment")
            else:
                reasons.append("EMA bearish alignment")
        
        if 'rsi' in df.columns:
            rsi = df['rsi'].iloc[-1]
            if rsi > 70:
                reasons.append("RSI overbought")
            elif rsi < 30:
                reasons.append("RSI oversold")
        
        # Add ADX context if available
        if ADVANCED_ANALYSIS.use_adx and f'adx_{ADVANCED_ANALYSIS.adx_period}' in df.columns:
            adx = df[f'adx_{ADVANCED_ANALYSIS.adx_period}'].iloc[-1]
            if adx > 25:
                reasons.append(f"Strong trend (ADX: {adx:.1f})")
        
        # Add probability context
        prob_up = prediction_proba[1] if len(prediction_proba) > 1 else 0
        prob_down = prediction_proba[0] if len(prediction_proba) > 0 else 0
        
        if direction == PredictionDirection.UP:
            reasons.append(f"Bullish probability: {prob_up:.1%}")
        elif direction == PredictionDirection.DOWN:
            reasons.append(f"Bearish probability: {prob_down:.1%}")
        
        return "; ".join(reasons) if reasons else "Based on ML model analysis"


class PatternRecognitionEngine:
    """
    Chart pattern recognition system for detecting classic technical patterns.
    """
    
    def __init__(self):
        self.lookback_period = PREDICTION.pattern_lookback_period
    
    def detect_patterns(self, df: pd.DataFrame) -> list[PatternMatch]:
        """
        Detect chart patterns in the price data.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            List of detected patterns with confidence scores
        """
        if df.empty or len(df) < self.lookback_period:
            return []
        
        patterns = []
        
        try:
            # Detect various patterns
            patterns.extend(self._detect_double_top(df))
            patterns.extend(self._detect_double_bottom(df))
            patterns.extend(self._detect_head_shoulders(df))
            patterns.extend(self._detect_triangles(df))
            patterns.extend(self._detect_flags(df))
            
            # Filter by confidence threshold
            patterns = [p for p in patterns if p.confidence >= PREDICTION.pattern_confidence_threshold]
            
            # Sort by confidence
            patterns.sort(key=lambda x: x.confidence, reverse=True)
            
            return patterns[:5]  # Return top 5 patterns
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error detecting patterns: {e}")
            return []
    
    def _detect_double_top(self, df: pd.DataFrame) -> list[PatternMatch]:
        """Detect double top pattern"""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        try:
            recent_data = df.tail(30)
            highs = recent_data['high'].values
            
            # Find two peaks of similar height
            peaks = []
            for i in range(2, len(highs) - 2):
                if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
                   highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                    peaks.append((i, highs[i]))
            
            if len(peaks) >= 2:
                # Check if two most recent peaks are similar height
                peak1, peak2 = peaks[-2], peaks[-1]
                height_diff = abs(peak1[1] - peak2[1]) / peak1[1]
                
                if height_diff < 0.02:  # Within 2%
                    confidence = 0.8 - height_diff * 10
                    _ = df['close'].iloc[-1]
                    neckline = min(recent_data['low'].iloc[peak1[0]:peak2[0]])
                    
                    patterns.append(PatternMatch(
                        pattern_name="Double Top",
                        confidence=max(0.5, confidence),
                        direction=PredictionDirection.DOWN,
                        target_price=neckline,
                        stop_loss_level=max(peak1[1], peak2[1]) * 1.01,
                        completion_pct=0.8,
                        timeframe="H1"
                    ))
        
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.debug(f"Error detecting double top: {e}")
        
        return patterns
    
    def _detect_double_bottom(self, df: pd.DataFrame) -> list[PatternMatch]:
        """Detect double bottom pattern"""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        try:
            recent_data = df.tail(30)
            lows = recent_data['low'].values
            
            # Find two troughs of similar depth
            troughs = []
            for i in range(2, len(lows) - 2):
                if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
                   lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                    troughs.append((i, lows[i]))
            
            if len(troughs) >= 2:
                trough1, trough2 = troughs[-2], troughs[-1]
                depth_diff = abs(trough1[1] - trough2[1]) / trough1[1]
                
                if depth_diff < 0.02:
                    confidence = 0.8 - depth_diff * 10
                    _ = df['close'].iloc[-1]
                    neckline = max(recent_data['high'].iloc[trough1[0]:trough2[0]])
                    
                    patterns.append(PatternMatch(
                        pattern_name="Double Bottom",
                        confidence=max(0.5, confidence),
                        direction=PredictionDirection.UP,
                        target_price=neckline,
                        stop_loss_level=min(trough1[1], trough2[1]) * 0.99,
                        completion_pct=0.8,
                        timeframe="H1"
                    ))
        
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.debug(f"Error detecting double bottom: {e}")
        
        return patterns
    
    def _detect_head_shoulders(self, df: pd.DataFrame) -> list[PatternMatch]:
        """Detect head and shoulders pattern (simplified)"""
        patterns = []
        
        if len(df) < 50:
            return patterns
        
        try:
            recent_data = df.tail(50)
            highs = recent_data['high'].values
            
            # Look for 3 peaks with middle one highest
            peaks = []
            for i in range(3, len(highs) - 3):
                if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i-3] and \
                   highs[i] > highs[i+1] and highs[i] > highs[i+2] and highs[i] > highs[i+3]:
                    peaks.append((i, highs[i]))
            
            if len(peaks) >= 3:
                # Check if middle peak is highest
                peak1, peak2, peak3 = peaks[-3], peaks[-2], peaks[-1]
                
                if peak2[1] > peak1[1] and peak2[1] > peak3[1]:
                    # Check if outer peaks are similar height
                    shoulder_diff = abs(peak1[1] - peak3[1]) / peak1[1]
                    
                    if shoulder_diff < 0.03:
                        confidence = 0.75 - shoulder_diff * 5
                        neckline = min(recent_data['low'].iloc[peak1[0]:peak3[0]])
                        
                        patterns.append(PatternMatch(
                            pattern_name="Head and Shoulders",
                            confidence=max(0.5, confidence),
                            direction=PredictionDirection.DOWN,
                            target_price=neckline,
                            stop_loss_level=peak2[1] * 1.01,
                            completion_pct=0.7,
                            timeframe="H1"
                        ))
        
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.debug(f"Error detecting head and shoulders: {e}")
        
        return patterns
    
    def _detect_triangles(self, df: pd.DataFrame) -> list[PatternMatch]:
        """Detect triangle patterns (ascending, descending, symmetrical)"""
        patterns = []
        
        if len(df) < 20:
            return patterns
        
        try:
            recent_data = df.tail(20)
            
            # Calculate trend lines
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            
            # Check for converging trend lines
            high_slope = np.polyfit(range(len(highs)), highs, 1)[0]
            low_slope = np.polyfit(range(len(lows)), lows, 1)[0]
            
            # Ascending triangle: flat top, rising bottom
            if abs(high_slope) < 0.0001 and low_slope > 0:
                patterns.append(PatternMatch(
                    pattern_name="Ascending Triangle",
                    confidence=0.7,
                    direction=PredictionDirection.UP,
                    target_price=highs.max(),
                    stop_loss_level=lows.min(),
                    completion_pct=0.6,
                    timeframe="H1"
                ))
            
            # Descending triangle: falling top, flat bottom
            elif high_slope < 0 and abs(low_slope) < 0.0001:
                patterns.append(PatternMatch(
                    pattern_name="Descending Triangle",
                    confidence=0.7,
                    direction=PredictionDirection.DOWN,
                    target_price=lows.min(),
                    stop_loss_level=highs.max(),
                    completion_pct=0.6,
                    timeframe="H1"
                ))
            
            # Symmetrical triangle: converging lines
            elif high_slope < 0 and low_slope > 0:
                convergence_rate = abs(high_slope) + low_slope
                if convergence_rate > 0.0001:
                    patterns.append(PatternMatch(
                        pattern_name="Symmetrical Triangle",
                        confidence=0.6,
                        direction=PredictionDirection.SIDEWAYS,
                        target_price=None,
                        stop_loss_level=None,
                        completion_pct=0.5,
                        timeframe="H1"
                    ))
        
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.debug(f"Error detecting triangles: {e}")
        
        return patterns
    
    def _detect_flags(self, df: pd.DataFrame) -> list[PatternMatch]:
        """Detect flag and pennant patterns"""
        patterns = []
        
        if len(df) < 15:
            return patterns
        
        try:
            recent_data = df.tail(15)
            
            # Simple flag detection: consolidation after strong move
            price_range = (recent_data['high'].max() - recent_data['low'].min()) / recent_data['close'].iloc[-1]
            
            if price_range < 0.005:  # Tight consolidation
                # Determine direction based on preceding trend
                preceding_data = df.tail(30).head(15)
                preceding_trend = (preceding_data['close'].iloc[-1] - preceding_data['close'].iloc[0]) / preceding_data['close'].iloc[0]
                
                if preceding_trend > 0.01:  # Bullish flag
                    patterns.append(PatternMatch(
                        pattern_name="Bull Flag",
                        confidence=0.65,
                        direction=PredictionDirection.UP,
                        target_price=recent_data['close'].iloc[-1] * (1 + abs(preceding_trend)),
                        stop_loss_level=recent_data['low'].min(),
                        completion_pct=0.7,
                        timeframe="H1"
                    ))
                elif preceding_trend < -0.01:  # Bearish flag
                    patterns.append(PatternMatch(
                        pattern_name="Bear Flag",
                        confidence=0.65,
                        direction=PredictionDirection.DOWN,
                        target_price=recent_data['close'].iloc[-1] * (1 - abs(preceding_trend)),
                        stop_loss_level=recent_data['high'].max(),
                        completion_pct=0.7,
                        timeframe="H1"
                    ))
        
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.debug(f"Error detecting flags: {e}")
        
        return patterns


class VolatilityForecaster:
    """
    Volatility forecasting using statistical methods and GARCH models (optional).
    """
    
    def __init__(self):
        self.horizon = PREDICTION.volatility_forecast_horizon
    
    def forecast_volatility(self, df: pd.DataFrame) -> VolatilityForecast:
        """
        Forecast future volatility based on historical patterns.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            VolatilityForecast with predicted volatility and regime
        """
        if df.empty or len(df) < 50:
            return VolatilityForecast(
                expected_volatility=0.0,
                volatility_regime="unknown",
                forecast_horizon=f"{self.horizon} bars",
                breakout_probability=0.0,
                expected_range=(0.0, 0.0),
                confidence=0.0
            )
        
        try:
            # Calculate historical volatility
            returns = df['close'].pct_change().dropna()
            
            if len(returns) < 20:
                return self._default_forecast(df)
            
            # Use multiple volatility measures
            rolling_vol = returns.rolling(20).std()
            ewma_vol = returns.ewm(span=20).std()
            
            current_vol = rolling_vol.iloc[-1] if len(rolling_vol) > 0 else 0.0
            ewma_current = ewma_vol.iloc[-1] if len(ewma_vol) > 0 else 0.0
            
            # Average for forecast
            forecast_vol = (current_vol + ewma_current) / 2
            
            # Determine volatility regime
            if forecast_vol > 0.03:
                regime = "high"
            elif forecast_vol > 0.015:
                regime = "normal"
            else:
                regime = "low"
            
            # Calculate breakout probability based on volatility squeeze
            vol_squeeze = current_vol / returns.rolling(50).std().iloc[-1] if len(returns) >= 50 else 1.0
            breakout_prob = max(0.0, min(1.0, (1.0 - vol_squeeze) * 2))
            
            # Calculate expected range
            current_price = df['close'].iloc[-1]
            expected_range = (
                current_price * (1 - forecast_vol * self.horizon),
                current_price * (1 + forecast_vol * self.horizon)
            )
            
            # Confidence based on data quality
            confidence = min(1.0, len(returns) / 100)
            
            return VolatilityForecast(
                expected_volatility=float(forecast_vol),
                volatility_regime=regime,
                forecast_horizon=f"{self.horizon} bars",
                breakout_probability=float(breakout_prob),
                expected_range=expected_range,
                confidence=float(confidence)
            )
            
        except Exception as e:  # noqa: BLE001 - catch any failure
            logger.error(f"Error forecasting volatility: {e}")
            return self._default_forecast(df)
    
    def _default_forecast(self, df: pd.DataFrame) -> VolatilityForecast:
        """Default forecast when analysis fails"""
        current_price = df['close'].iloc[-1] if not df.empty else 1.0
        default_vol = 0.01  # 1% default volatility
        
        return VolatilityForecast(
            expected_volatility=default_vol,
            volatility_regime="normal",
            forecast_horizon=f"{self.horizon} bars",
            breakout_probability=0.3,
            expected_range=(current_price * 0.99, current_price * 1.01),
            confidence=0.3
        )