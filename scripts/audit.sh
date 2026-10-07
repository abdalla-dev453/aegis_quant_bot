#!/usr/bin/env bash
# scripts/audit.sh — Milestone sign-off audit for aegis_quant
# Run from the repo root:  bash scripts/audit.sh
# Exit 0 = clean; Exit 1 = one or more checks failed.
set -euo pipefail
fail=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_PYTHON="$ROOT/.venv/bin/python"
VENV_RUFF="$ROOT/.venv/bin/ruff"

# ── colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
fail_msg() { echo -e "${RED}  ❌ $1${NC}"; fail=1; }

echo "========================================================"
echo "  aegis_quant — Milestone Audit  $(date '+%Y-%m-%d %H:%M')"
echo "========================================================"

# Helper runner: search with rg or grep
search_pattern() {
  local pattern="$1"
  shift
  if command -v rg &>/dev/null; then
    rg -n "$pattern" --pcre2 "$@" 2>/dev/null || true
  else
    grep -rnE "$pattern" "$@" 2>/dev/null || true
  fi
}

# ── 1. Untracked TODO/FIXME (only TODO(phase-N) allowed) ───────────────────
echo ""
echo "== 1. Untracked TODO/FIXME (must be TODO(phase-N) only) =="
TODO_MATCHES=$(search_pattern "TODO\([a-zA-Z]|FIXME|XXX|HACK" lib/ea-bridge/app ea)
if [ -n "$TODO_MATCHES" ]; then
  fail_msg "Untracked TODO/FIXME markers found:\n$TODO_MATCHES"
else
  pass "No untracked TODO/FIXME markers"
fi

# ── 2. Forbidden Python anti-patterns ──────────────────────────────────────
echo ""
echo "== 2. Forbidden Python anti-patterns =="
BARE_EXCEPT=$(search_pattern "except\s*:\s*$" lib/ea-bridge/app)
if [ -n "$BARE_EXCEPT" ]; then
  fail_msg "Bare except clauses found:\n$BARE_EXCEPT"
else
  pass "No bare except clauses"
fi

# ── 3. Empty except blocks ──────────────────────────────────────────────────
echo ""
echo "== 3. Empty except / catch blocks =="
EMPTY_EXCEPT=$(grep -rnA 1 -E "except.*:" lib/ea-bridge/app | grep -B 1 -E "\s+pass\s*$" || true)
if [ -n "$EMPTY_EXCEPT" ]; then
  fail_msg "Empty except blocks found:\n$EMPTY_EXCEPT"
else
  pass "No empty except blocks"
fi

# ── 4. Mock/lorem data outside fixtures ────────────────────────────────────
echo ""
echo "== 4. Mock / lorem data outside fixtures =="
LOREM_MATCHES=$(search_pattern "lorem ipsum|fakeData" lib/ea-bridge/app)
if [ -n "$LOREM_MATCHES" ]; then
  fail_msg "Mock/lorem data found outside fixtures:\n$LOREM_MATCHES"
else
  pass "No stray mock/lorem data"
fi

# ── 5. Secrets accidentally logged ──────────────────────────────────────────
echo ""
echo "== 5. Secrets accidentally logged =="
SECRET_LOGS=$(search_pattern "log.*(device_token|raw_token|password_hash|secret)" lib/ea-bridge/app ea)
if [ -n "$SECRET_LOGS" ]; then
  fail_msg "Potential secret logging detected:\n$SECRET_LOGS"
else
  pass "No secrets logged"
fi

# ── 6. Every API route has a test ──────────────────────────────────────────
echo ""
echo "== 6. Every API route has a test =="
if [ -f "scripts/route-coverage.mjs" ]; then
  if node scripts/route-coverage.mjs; then
    pass "All API routes covered by tests"
  else
    fail_msg "Some API routes have no test"
  fi
fi

# ── 7. Every error code is tested ──────────────────────────────────────────
echo ""
echo "== 7. Every error code is tested =="
if [ -f "scripts/error-coverage.mjs" ]; then
  if node scripts/error-coverage.mjs; then
    pass "All error codes covered by tests"
  else
    fail_msg "Some error codes have no test"
  fi
fi

# ── 8. Python lint (ruff) ───────────────────────────────────────────────────
echo ""
echo "== 8. Python lint (ruff) =="
if [ -x "$VENV_RUFF" ]; then
  if "$VENV_RUFF" check lib/ea-bridge/app --quiet; then
    pass "ruff lint clean"
  else
    fail_msg "ruff lint errors found"
  fi
elif command -v ruff &>/dev/null; then
  if ruff check lib/ea-bridge/app --quiet; then
    pass "ruff lint clean"
  else
    fail_msg "ruff lint errors found"
  fi
else
  warn "ruff not found — skipping lint check 8"
fi

# ── 9. EA source file present ───────────────────────────────────────────────
echo ""
echo "== 9. EA source file present =="
if [ -f "ea/AegisQuantEA.mq5" ]; then
  EA_LINES=$(wc -l < "ea/AegisQuantEA.mq5")
  pass "ea/AegisQuantEA.mq5 present (${EA_LINES} lines)"
else
  fail_msg "ea/AegisQuantEA.mq5 missing"
fi

# ── 10. Traceability matrix consistency ─────────────────────────────────────
echo ""
echo "== 10. Traceability matrix consistency =="
if [ -f "docs/TRACEABILITY.md" ]; then
  # Only inspect feature task rows (starting with | B- or | E- or | W-) with 6 columns
  BAD_ROWS=$(grep -E "^\| (B|E|W)-" docs/TRACEABILITY.md | grep "✅" | awk -F'|' '{
    code=$4; test=$5; demo=$6;
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", code);
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", test);
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", demo);
    if (code == "—" || code == "" || test == "—" || test == "" || demo == "—" || demo == "") print $0
  }' || true)
  if [ -n "$BAD_ROWS" ]; then
    fail_msg "Rows marked ✅ with incomplete evidence:\n$BAD_ROWS"
  else
    pass "Traceability matrix is consistent"
  fi
else
  fail_msg "docs/TRACEABILITY.md missing"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "========================================================"
if [ "$fail" -eq 0 ]; then
  echo -e "${GREEN}  ✅  All checks passed — milestone audit clean.${NC}"
else
  echo -e "${RED}  ❌  One or more checks FAILED — fix before signing off.${NC}"
fi
echo "========================================================"

exit $fail
