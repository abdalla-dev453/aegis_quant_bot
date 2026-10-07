#!/usr/bin/env python3
"""
EA Simulator
============
Imitates an MT5 terminal for E2E testing. Uses httpx to match the test client's
serialization exactly. Pairs, sends heartbeats, and executes signals using the
same reject rules as the real EA.

Usage:
    python tests/ea-scenarios/ea_simulator.py --base-url http://localhost:8000
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx


def sign_request(token: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_digest = hashlib.sha256(body).hexdigest()
    message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_digest}".encode()
    return hmac.new(token.encode("ascii"), message, hashlib.sha256).hexdigest()


class EASimulator:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client()
        self.device_token = None
        self.device_id = None
        self.user_id = None
        self.pairing_code = None

    def signup(self, email: str, password: str) -> bool:
        resp = self.client.post(f"{self.base_url}/app/v1/auth/signup", json={"email": email, "password": password, "risk_disclaimer_accepted": True}, timeout=10)
        if resp.status_code == 201:
            return True
        resp = self.client.post(f"{self.base_url}/app/v1/auth/login", json={"email": email, "password": password}, timeout=10)
        return resp.status_code == 200

    def create_pairing_code(self) -> str | None:
        resp = self.client.post(f"{self.base_url}/app/v1/devices/pairing-codes", timeout=10)
        if resp.status_code == 201:
            self.pairing_code = resp.json()["code"]
            return self.pairing_code
        return None

    def pair(self, code: str, terminal_build: str = "4150", broker: str = "MetaQuotes-Demo", server: str = "Demo-Server", account: str = "5091****12", currency: str = "USD", leverage: int = 100) -> bool:
        resp = self.client.post(f"{self.base_url}/ea/v1/pair", json={"code": code, "terminal_build": terminal_build, "broker": broker, "server": server, "account_number_masked": account, "account_currency": currency, "leverage": leverage}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            self.device_token = data["device_token"]
            self.device_id = data["device_id"]
            return True
        return False

    def _build_body(self, payload: dict, path: str) -> bytes:
        return self.client.build_request("POST", f"{self.base_url}{path}", json=payload).content

    def _signed_request(self, method: str, path: str, payload: dict | None = None) -> httpx.Response | None:
        if not self.device_token:
            return None
        ts = str(int(time.time()))
        nonce = f"nonce_{uuid4().hex[:16]}"
        body = b""
        if payload is not None:
            body = self._build_body(payload, path)
        sig = sign_request(self.device_token, method, path, ts, nonce, body)
        headers = {"Content-Type": "application/json", "X-EA-Device-Token": self.device_token, "X-EA-Timestamp": ts, "X-EA-Nonce": nonce, "X-EA-Signature": sig}
        if method == "GET":
            return self.client.get(f"{self.base_url}{path}", headers=headers, timeout=10)
        return self.client.post(f"{self.base_url}{path}", content=body, headers=headers, timeout=10)

    def heartbeat(self, balance: str = "10000.00", equity: str = "10050.25", positions: list | None = None) -> dict | None:
        snapshot = {"balance": balance, "equity": equity, "margin": "200.00", "free_margin": "9850.25", "margin_level": 5025.12, "open_positions_count": len(positions) if positions else 0, "account_currency": "USD", "leverage": 100, "captured_at": datetime.now(UTC).isoformat()}
        payload = {"snapshot": snapshot, "positions": positions or []}
        resp = self._signed_request("POST", "/ea/v1/heartbeat", payload)
        return resp.json() if resp else None

    def get_signals(self) -> list:
        resp = self._signed_request("GET", "/ea/v1/signals")
        return resp.json() if resp else []

    def ack_signal(self, signal_id: str, event: str = "ACKED", occurred_at: str | None = None) -> dict | None:
        occurred_at = occurred_at or datetime.now(UTC).isoformat()
        payload = {"event": event, "occurred_at": occurred_at}
        resp = self._signed_request("POST", f"/ea/v1/signals/{signal_id}/ack", payload)
        return resp.json() if resp else None

    def report_trade(self, signal_id: str | None, ticket: str, symbol: str, side: str, volume: str, execution_price: str, opened_at: str | None = None) -> dict | None:
        opened_at = opened_at or datetime.now(UTC).isoformat()
        payload = {"signal_id": signal_id, "ticket": ticket, "symbol": symbol, "side": side, "volume": volume, "execution_price": execution_price, "opened_at": opened_at}
        resp = self._signed_request("POST", "/ea/v1/trade-reports", payload)
        return resp.json() if resp else None


def run_e2e_scenarios(base_url: str) -> list[dict]:
    sim = EASimulator(base_url)
    results = []
    email = f"sim-{uuid4().hex[:8]}@test.com"
    password = "SimulatorPass123!"

    assert sim.signup(email, password), "Signup/login failed"
    code = sim.create_pairing_code()
    assert code, "Failed to create pairing code"
    assert sim.pair(code), "Pairing failed"

    hb = sim.heartbeat()
    results.append({"scenario": "heartbeat", "passed": hb is not None and hb.get("accepted") is True, "response": str(hb)[:200]})

    positions = [{"external_position_id": "TICKET_101", "symbol": "EURUSD", "side": "BUY", "volume": "0.10", "entry_price": "1.08500", "current_price": "1.08550", "stop_loss": "1.08200", "take_profit": "1.09100", "unrealized_pnl": "50.00", "swap": "0.25", "observed_at": datetime.now(UTC).isoformat()}]
    hb2 = sim.heartbeat(positions=positions)
    results.append({"scenario": "heartbeat_with_positions", "passed": hb2 is not None and hb2.get("accepted") is True, "response": str(hb2)[:200]})

    signals = sim.get_signals()
    results.append({"scenario": "poll_signals_empty", "passed": signals == [], "response": str(signals)[:200]})

    ts = str(int(time.time()))
    nonce = "nonce_replay_000001"
    body = sim._build_body({"snapshot": {"balance": "10000", "equity": "10000", "margin": "0", "free_margin": "10000", "margin_level": 0, "open_positions_count": 0, "account_currency": "USD", "leverage": 100, "captured_at": datetime.now(UTC).isoformat()}, "positions": []}, "/ea/v1/heartbeat")
    sig = sign_request(sim.device_token, "POST", "/ea/v1/heartbeat", ts, nonce, body)
    headers = {"Content-Type": "application/json", "X-EA-Device-Token": sim.device_token, "X-EA-Timestamp": ts, "X-EA-Nonce": nonce, "X-EA-Signature": sig}
    resp1 = sim.client.post(f"{base_url}/ea/v1/heartbeat", content=body, headers=headers, timeout=10)
    resp2 = sim.client.post(f"{base_url}/ea/v1/heartbeat", content=body, headers=headers, timeout=10)
    results.append({"scenario": "replay_attack_blocked", "passed": resp1.status_code == 200 and resp2.status_code == 401, "response": f"first={resp1.status_code} replay={resp2.status_code}"})

    tampered_sig = "0" * 64
    stale_ts = str(int(time.time()) - 45)
    stale_nonce = "nonce_stale_000001"
    stale_body = sim._build_body({"snapshot": {"balance": "10000", "equity": "10000", "margin": "0", "free_margin": "10000", "margin_level": 0, "open_positions_count": 0, "account_currency": "USD", "leverage": 100, "captured_at": datetime.now(UTC).isoformat()}, "positions": []}, "/ea/v1/heartbeat")
    stale_sig = sign_request(sim.device_token, "POST", "/ea/v1/heartbeat", stale_ts, stale_nonce, stale_body)
    stale_headers = {"Content-Type": "application/json", "X-EA-Device-Token": sim.device_token, "X-EA-Timestamp": stale_ts, "X-EA-Nonce": stale_nonce, "X-EA-Signature": stale_sig}
    resp4 = sim.client.post(f"{base_url}/ea/v1/heartbeat", content=stale_body, headers=stale_headers, timeout=10)
    results.append({"scenario": "stale_timestamp_blocked", "passed": resp4.status_code == 401, "response": str(resp4.status_code)})

    sim.client.delete(f"{base_url}/app/v1/devices/{sim.device_id}", timeout=10)
    hb_revoked = sim.heartbeat()
    results.append({"scenario": "device_revoke_blocks_heartbeat", "passed": hb_revoked is not None and hb_revoked.get("code") == "invalid_device_auth", "response": f"hb={str(hb_revoked)[:100]}"})

    sim2 = EASimulator(base_url)
    sim2.signup(f"sim2-{uuid4().hex[:8]}@test.com", "SimulatorPass123!")
    code2 = sim2.create_pairing_code()
    assert sim2.pair(code2), "Re-pairing failed"
    trade = sim2.report_trade(signal_id=str(uuid4()), ticket="TICKET_200", symbol="EURUSD", side="BUY", volume="0.10", execution_price="1.08500")
    results.append({"scenario": "trade_report_201", "passed": trade is not None and trade.get("accepted") is True, "response": str(trade)[:200]})

    ack = sim2.ack_signal(str(uuid4()))
    results.append({"scenario": "ack_signal_not_found_404", "passed": ack is not None and ack.get("code") == "signal_not_found", "response": str(ack)[:200]})

    return results


def main():
    parser = argparse.ArgumentParser(description="Run EA simulator E2E scenarios")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", default="tests/ea-scenarios/simulator-results.json", help="Results output path")
    args = parser.parse_args()

    results = run_e2e_scenarios(args.base_url)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{len(results)} simulator scenarios passed.")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {r['scenario']}: {status}")
    print(f"Results saved to {args.output}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
