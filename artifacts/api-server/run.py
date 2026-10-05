"""Serve the imported Python APIs through the artifact's assigned port.

Only the monitoring API starts here. The trading runner is deliberately not
started: this Linux workspace is not a qualified broker/MT5 execution host.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "trading-engine"))
sys.path.insert(0, str(ROOT / "lib" / "ea-bridge"))

# Runtime-only authentication: never expose this value to Vite or the browser.
if not os.environ.get("API_TOKEN"):
    if not os.environ.get("SESSION_SECRET"):
        raise RuntimeError("Configure API_TOKEN in Replit Secrets before starting the API.")
    os.environ["API_TOKEN"] = os.environ["SESSION_SECRET"]

from api import app as bot_app
from data_provider import MT5ConnectionError


@bot_app.exception_handler(MT5ConnectionError)
async def mt5_unavailable(request: Request, error: MT5ConnectionError):
    return JSONResponse(status_code=503, content={"detail": str(error)})


# Preserve the external PostgreSQL/Redis architecture; do not create substitute
# stores or silently migrate the user's data to a different database.
bridge_app = None
if os.environ.get("DATABASE_URL") and os.environ.get("REDIS_URL"):
    from app.main import app as bridge_app


# Preserve the original EA paths, including the HMAC-signed request path.
# When configured, the bridge retains its own lifespan and state unchanged.
app = bridge_app if bridge_app is not None else FastAPI(title="Onyx FX Replit API")


@app.get("/api/healthz")
async def health():
    return {"status": "ok", "tradingRunnerStarted": False,
            "eaBridgeConfigured": bridge_app is not None}


if bridge_app is None:
    @app.api_route("/app/v1/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
    @app.api_route("/ea/v1/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
    async def bridge_not_configured(path: str):
        return JSONResponse(status_code=503, content={
            "code": "BRIDGE_NOT_CONFIGURED",
            "message": "The EA bridge requires its original PostgreSQL DATABASE_URL and Redis REDIS_URL."
        })

app.mount("/", bot_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ["PORT"]),
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")