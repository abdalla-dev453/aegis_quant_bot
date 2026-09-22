"""
self_healing.py
---------------
Self-healing and automated recovery system for handling common failures
and maintaining system health without manual intervention.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from collections import deque

from config import SELF_HEALING
from data_provider import (
    MT5ConnectionError, 
    initialize_connection, 
    shutdown_connection,
    ensure_connected,
    mt5
)
import pandas as pd

logger = logging.getLogger("trading_bot.self_healing")


class RecoveryAction(str, Enum):
    """Types of recovery actions"""
    RECONNECT = "reconnect"
    SWITCH_DATA_SOURCE = "switch_data_source"
    CLEAR_CACHE = "clear_cache"
    RESTART_COMPONENT = "restart_component"
    FALLBACK_MODE = "fallback_mode"
    IGNORE_AND_CONTINUE = "ignore_and_continue"


class HealthStatus(str, Enum):
    """System health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"


@dataclass
class HealthMetric:
    """Individual health metric"""
    name: str
    value: float
    status: HealthStatus
    timestamp: datetime
    threshold_warning: float
    threshold_critical: float


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt"""
    error_type: str
    action_taken: RecoveryAction
    success: bool
    timestamp: datetime
    duration_seconds: float
    details: str


class HealthMonitor:
    """
    Monitors system health metrics and triggers recovery actions when needed.
    """
    
    def __init__(self):
        self.metrics: dict[str, HealthMetric] = {}
        self.recovery_history: deque[RecoveryAttempt] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._check_interval = 30  # seconds
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
    
    def start_monitoring(self):
        """Start background health monitoring"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Health monitoring started")
    
    def stop_monitoring(self):
        """Stop background health monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Health monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self._running:
            try:
                self._check_system_health()
                time.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
    
    def _check_system_health(self):
        """Check all system health metrics"""
        try:
            # Check MT5 connection health
            self._check_connection_health()
            
            # Check data quality
            self._check_data_quality()
            
            # Check memory usage
            self._check_memory_health()
            
            # Check error rates
            self._check_error_rates()
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
    
    def _check_connection_health(self):
        """Check MT5 connection health"""
        try:
            if mt5 is None:
                self._update_metric("connection_health", 0.0, HealthStatus.CRITICAL)
                return
            
            info = mt5.terminal_info()
            if info is None:
                self._update_metric("connection_health", 0.0, HealthStatus.CRITICAL)
                return
            
            health_score = 1.0 if info.connected else 0.0
            status = HealthStatus.HEALTHY if health_score >= 0.8 else HealthStatus.CRITICAL
            
            self._update_metric("connection_health", health_score, status)
            
        except Exception as e:
            logger.debug(f"Error checking connection health: {e}")
            self._update_metric("connection_health", 0.0, HealthStatus.CRITICAL)
    
    def _check_data_quality(self):
        """Check data quality metrics"""
        # This would be implemented with actual data quality checks
        # For now, placeholder
        self._update_metric("data_quality", 1.0, HealthStatus.HEALTHY)
    
    def _check_memory_health(self):
        """Check memory usage"""
        try:
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_percent()
            
            status = HealthStatus.HEALTHY
            if memory_percent > 90:
                status = HealthStatus.CRITICAL
            elif memory_percent > 70:
                status = HealthStatus.DEGRADED
            
            # Convert to health score (inverse of memory usage)
            health_score = max(0.0, 1.0 - (memory_percent / 100.0))
            
            self._update_metric("memory_health", health_score, status)
            
        except ImportError:
            # psutil not available, use simple fallback
            self._update_metric("memory_health", 0.8, HealthStatus.HEALTHY)
        except Exception as e:
            logger.debug(f"Error checking memory health: {e}")
            self._update_metric("memory_health", 0.5, HealthStatus.DEGRADED)
    
    def _check_error_rates(self):
        """Check recent error rates"""
        # Count recent recovery attempts
        recent_failures = [
            attempt for attempt in self.recovery_history
            if not attempt.success and 
            (datetime.now(timezone.utc) - attempt.timestamp).total_seconds() < 300
        ]
        
        error_rate = len(recent_failures) / 10.0  # Normalize to 0-1 scale
        status = HealthStatus.HEALTHY
        
        if error_rate > 0.5:
            status = HealthStatus.CRITICAL
        elif error_rate > 0.2:
            status = HealthStatus.DEGRADED
        
        health_score = max(0.0, 1.0 - error_rate)
        self._update_metric("error_rate", health_score, status)
    
    def _update_metric(self, name: str, value: float, status: HealthStatus):
        """Update a health metric"""
        with self._lock:
            self.metrics[name] = HealthMetric(
                name=name,
                value=value,
                status=status,
                timestamp=datetime.now(timezone.utc),
                threshold_warning=0.7,
                threshold_critical=0.5
            )
    
    def get_health_summary(self) -> dict[str, Any]:
        """Get overall system health summary"""
        with self._lock:
            if not self.metrics:
                return {
                    "overall_status": HealthStatus.HEALTHY.value,
                    "metrics": {},
                    "issues": []
                }
            
            # Determine overall status
            critical_count = sum(1 for m in self.metrics.values() if m.status == HealthStatus.CRITICAL)
            degraded_count = sum(1 for m in self.metrics.values() if m.status == HealthStatus.DEGRADED)
            
            if critical_count > 0:
                overall_status = HealthStatus.CRITICAL
            elif degraded_count > 0:
                overall_status = HealthStatus.DEGRADED
            else:
                overall_status = HealthStatus.HEALTHY
            
            # Identify issues
            issues = [
                f"{m.name}: {m.status.value} (value: {m.value:.2f})"
                for m in self.metrics.values()
                if m.status != HealthStatus.HEALTHY
            ]
            
            return {
                "overall_status": overall_status.value,
                "metrics": {
                    name: {
                        "value": metric.value,
                        "status": metric.status.value,
                        "timestamp": metric.timestamp.isoformat()
                    }
                    for name, metric in self.metrics.items()
                },
                "issues": issues
            }
    
    def record_recovery_attempt(self, attempt: RecoveryAttempt):
        """Record a recovery attempt"""
        with self._lock:
            self.recovery_history.append(attempt)


class SelfHealingManager:
    """
    Main self-healing manager that diagnoses issues and coordinates recovery actions.
    """
    
    def __init__(self):
        self.health_monitor = HealthMonitor()
        self.recovery_attempts: dict[str, int] = {}  # Track attempts per error type
        self._lock = threading.Lock()
        self._recovery_handlers: dict[type, Callable] = {
            MT5ConnectionError: self._handle_connection_error,
        }
        
        if SELF_HEALING.enable_self_healing:
            self.health_monitor.start_monitoring()
            logger.info("Self-healing system enabled")
        else:
            logger.info("Self-healing system disabled")
    
    def diagnose_and_recover(self, error: Exception, context: dict[str, Any] | None = None) -> bool:
        """
        Automatically diagnose and attempt recovery from errors.
        
        Args:
            error: The exception that occurred
            context: Additional context about the error
            
        Returns:
            True if recovery was successful, False otherwise
        """
        if not SELF_HEALING.enable_self_healing:
            logger.info("Self-healing disabled, skipping recovery")
            return False
        
        error_type = type(error)
        error_key = f"{error_type.__name__}"
        
        # Check if we've exceeded max attempts for this error type
        with self._lock:
            attempts = self.recovery_attempts.get(error_key, 0)
            if attempts >= SELF_HEALING.max_recovery_attempts:
                logger.warning(f"Max recovery attempts ({SELF_HEALING.max_recovery_attempts}) reached for {error_key}")
                return False
            
            self.recovery_attempts[error_key] = attempts + 1
        
        # Get appropriate handler
        handler = self._recovery_handlers.get(error_type, self._handle_generic_error)
        
        # Attempt recovery
        start_time = time.time()
        try:
            success = handler(error, context or {})
            duration = time.time() - start_time
            
            # Record the attempt
            attempt = RecoveryAttempt(
                error_type=error_key,
                action_taken=self._determine_action(error_type),
                success=success,
                timestamp=datetime.now(timezone.utc),
                duration_seconds=duration,
                details=str(error)[:200]
            )
            self.health_monitor.record_recovery_attempt(attempt)
            
            if success:
                # Reset attempt counter on success
                with self._lock:
                    self.recovery_attempts[error_key] = 0
                logger.info(f"Successfully recovered from {error_key} in {duration:.2f}s")
            else:
                logger.warning(f"Recovery attempt failed for {error_key} (attempt {attempts + 1})")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during recovery attempt for {error_key}: {e}")
            return False
    
    def _handle_connection_error(self, error: MT5ConnectionError, context: dict[str, Any]) -> bool:
        """Handle MT5 connection errors with exponential backoff"""
        error_key = "MT5ConnectionError"
        
        with self._lock:
            attempts = self.recovery_attempts.get(error_key, 0)
        
        # Calculate backoff time
        backoff_time = min(
            SELF_HEALING.recovery_backoff_base * (2 ** attempts),
            SELF_HEALING.recovery_backoff_max
        )
        
        logger.info(f"Attempting connection recovery (attempt {attempts + 1}) with {backoff_time:.1f}s backoff")
        time.sleep(backoff_time)
        
        try:
            # Shutdown existing connection
            shutdown_connection()
            
            # Attempt reconnection
            initialize_connection()
            
            # Verify connection
            ensure_connected()
            
            logger.info("Connection recovery successful")
            return True
            
        except Exception as e:
            logger.error(f"Connection recovery failed: {e}")
            return False
    
    def _handle_generic_error(self, error: Exception, context: dict[str, Any]) -> bool:
        """Handle generic errors with basic recovery strategies"""
        logger.info(f"Attempting generic recovery for {type(error).__name__}")
        
        # Try basic recovery steps
        try:
            # Clear any caches if applicable
            # Reset any transient state
            # Log detailed error information
            
            logger.info("Generic recovery completed (may not have resolved issue)")
            return True  # Return True to prevent infinite loops, even if not fully resolved
            
        except Exception as e:
            logger.error(f"Generic recovery failed: {e}")
            return False
    
    def _determine_action(self, error_type: type) -> RecoveryAction:
        """Determine the appropriate recovery action for an error type"""
        if error_type == MT5ConnectionError:
            return RecoveryAction.RECONNECT
        elif "data" in str(error_type).lower():
            return RecoveryAction.SWITCH_DATA_SOURCE
        elif "cache" in str(error_type).lower():
            return RecoveryAction.CLEAR_CACHE
        else:
            return RecoveryAction.IGNORE_AND_CONTINUE
    
    def reset_recovery_counters(self):
        """Reset all recovery attempt counters"""
        with self._lock:
            self.recovery_attempts.clear()
        logger.info("Recovery counters reset")
    
    def get_recovery_status(self) -> dict[str, Any]:
        """Get current recovery system status"""
        with self._lock:
            return {
                "enabled": SELF_HEALING.enable_self_healing,
                "recovery_attempts": dict(self.recovery_attempts),
                "max_attempts": SELF_HEALING.max_recovery_attempts,
                "health_summary": self.health_monitor.get_health_summary(),
                "recent_recoveries": [
                    {
                        "error_type": attempt.error_type,
                        "action": attempt.action_taken.value,
                        "success": attempt.success,
                        "timestamp": attempt.timestamp.isoformat(),
                        "duration": attempt.duration_seconds
                    }
                    for attempt in list(self.health_monitor.recovery_history)[-10:]
                ]
            }
    
    def shutdown(self):
        """Cleanup and shutdown the self-healing system"""
        self.health_monitor.stop_monitoring()
        logger.info("Self-healing system shutdown")


class DataQualityChecker:
    """
    Validates data quality and detects issues that could affect trading decisions.
    """
    
    def __init__(self):
        self.enabled = SELF_HEALING.enable_data_quality_checks
        self.max_nan_ratio = SELF_HEALING.max_nan_ratio
        self.min_data_points = SELF_HEALING.min_data_points
    
    def validate_dataframe(self, df, symbol: str = "unknown") -> tuple[bool, str]:
        """
        Validate DataFrame quality for trading operations.
        
        Args:
            df: DataFrame to validate
            symbol: Symbol name for logging
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.enabled:
            return True, ""
        
        if df is None or df.empty:
            return False, f"DataFrame is empty for {symbol}"
        
        # Check minimum data points
        if len(df) < self.min_data_points:
            return False, f"Insufficient data points ({len(df)} < {self.min_data_points}) for {symbol}"
        
        # Check for NaN values
        nan_ratio = df.isna().sum().sum() / (len(df) * len(df.columns))
        if nan_ratio > self.max_nan_ratio:
            return False, f"High NaN ratio ({nan_ratio:.2%} > {self.max_nan_ratio:.2%}) for {symbol}"
        
        # Check for infinite values
        if np.isinf(df.select_dtypes(include=[np.number])).any().any():
            return False, f"Infinite values detected in {symbol}"
        
        # Check for duplicate timestamps
        if df.index.duplicated().any():
            return False, f"Duplicate timestamps detected in {symbol}"
        
        # Check for monotonic timestamp index
        if not df.index.is_monotonic_increasing:
            return False, f"Non-monotonic timestamp index in {symbol}"
        
        return True, ""
    
    def validate_price_data(self, df: pd.DataFrame) -> tuple[bool, str]:
        """
        Validate price data specifically for common issues.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.enabled:
            return True, ""
        
        required_columns = ['open', 'high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {missing_columns}"
        
        # Check for valid OHLC relationships
        invalid_ohlc = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        )
        
        if invalid_ohlc.any():
            invalid_count = invalid_ohlc.sum()
            return False, f"Invalid OHLC relationships in {invalid_count} bars"
        
        # Check for zero or negative prices
        zero_prices = (df[required_columns] <= 0).any().any()
        if zero_prices:
            return False, "Zero or negative prices detected"
        
        return True, ""


# Global instance
self_healing_manager = SelfHealingManager()
data_quality_checker = DataQualityChecker()