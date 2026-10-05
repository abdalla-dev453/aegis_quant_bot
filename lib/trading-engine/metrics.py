"""Shared Prometheus metrics for the trading bot."""

from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS = Counter("aegis_api_requests_total", "Total API requests", ["method", "endpoint", "status"])
API_LATENCY = Histogram("aegis_api_latency_seconds", "API request latency", ["method", "endpoint"])
MT5_CONNECTED = Gauge("aegis_mt5_connected", "MT5 connection status (1=connected)")
MT5_LAST_CANDLE_AGE = Gauge("aegis_mt5_last_candle_age_seconds", "Age of last H1 candle in seconds")
AI_REQUESTS = Counter("aegis_ai_requests_total", "Total AI requests", ["result"])
AI_LATENCY = Histogram("aegis_ai_latency_seconds", "AI request latency")
ORDERS_PLACED = Counter("aegis_orders_placed_total", "Total orders placed", ["symbol", "direction", "result"])
POSITIONS_OPEN = Gauge("aegis_positions_open", "Current open positions")
EQUITY = Gauge("aegis_account_equity", "Account equity")
DRAWDOWN = Gauge("aegis_drawdown_percent", "Current drawdown percent")
