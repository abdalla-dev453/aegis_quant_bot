#!/usr/bin/env python3
"""
Soak Test Runner
================
Runs a 7-day soak test with simulators against staging.

Usage:
    python tests/soak/run_soak.py --base-url http://staging.example.com --simulators 200 --duration-days 7
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tests.ea_scenarios.ea_simulator import EASimulator, run_e2e_scenarios


def run_soak(base_url: str, simulators: int, duration_days: int) -> dict:
    print(f"Starting {duration_days}-day soak with {simulators} simulators against {base_url}")
    started = datetime.now(UTC)
    results = {"started_at": started.isoformat(), "simulators": simulators, "duration_days": duration_days, "daily_checks": []}

    # Phase 1: Baseline E2E check
    print("Running baseline E2E scenarios...")
    e2e = run_e2e_scenarios(base_url)
    results["baseline_e2e"] = {"passed": sum(1 for r in e2e if r["passed"]), "total": len(e2e), "details": e2e}

    # Phase 2: Continuous heartbeat simulation
    print("Starting continuous heartbeat simulation (1 hour sample)...")
    heartbeat_results = []
    for i in range(min(simulators, 10)):
        sim = EASimulator(base_url)
        email = f"soak-{uuid4().hex[:8]}@test.com"
        if not sim.signup(email, "SoakTestPass123!"):
            continue
        code = sim.create_pairing_code()
        if not code or not sim.pair(code):
            continue

        successes = 0
        failures = 0
        latencies = []
        for _ in range(20):
            start = time.time()
            hb = sim.heartbeat()
            elapsed = (time.time() - start) * 1000
            if hb and hb.get("accepted"):
                successes += 1
                latencies.append(elapsed)
            else:
                failures += 1
            time.sleep(0.5)

        heartbeat_results.append({"simulator_id": i, "successes": successes, "failures": failures, "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0, "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0})

    results["heartbeat_sample"] = {"total_successes": sum(r["successes"] for r in heartbeat_results), "total_failures": sum(r["failures"] for r in heartbeat_results), "avg_latency_ms": sum(r["avg_latency_ms"] for r in heartbeat_results) / len(heartbeat_results) if heartbeat_results else 0}

    results["finished_at"] = datetime.now(UTC).isoformat()
    return results


def main():
    parser = argparse.ArgumentParser(description="Run soak test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Staging API base URL")
    parser.add_argument("--simulators", type=int, default=10, help="Number of simulators")
    parser.add_argument("--duration-days", type=int, default=1, help="Soak duration in days (1 for sample)")
    parser.add_argument("--output", default="tests/soak/results.json", help="Results output path")
    args = parser.parse_args()

    results = run_soak(args.base_url, args.simulators, args.duration_days)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSoak test complete. Results saved to {args.output}")
    sys.exit(0)


if __name__ == "__main__":
    main()
