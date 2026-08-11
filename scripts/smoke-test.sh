#!/usr/bin/env bash
# smoke-test.sh — Validate that the ForgeGuard backend is alive and ready.
#
# Usage:
#   BASE_URL=http://localhost:8000 bash scripts/smoke-test.sh
#
# Exit codes:
#   0  All checks passed
#   1  One or more checks failed
#
# The script retries with exponential backoff (up to 60 seconds) before
# declaring failure, which accommodates services that are still starting up.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
MAX_WAIT=60         # total seconds to wait before giving up
INITIAL_DELAY=2     # seconds before first retry
MAX_DELAY=16        # cap on exponential backoff
PASS=0
FAIL=0

# ── Helpers ────────────────────────────────────────────────────────────────

log_pass() { echo "  PASS: $*"; PASS=$((PASS + 1)); }
log_fail() { echo "  FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# Wait for a URL to respond with 200, retrying with exponential backoff.
wait_for_url() {
  local url="$1"
  local elapsed=0
  local delay="$INITIAL_DELAY"

  while true; do
    if curl -sf --max-time 5 "$url" >/dev/null 2>&1; then
      return 0
    fi

    if [ "$elapsed" -ge "$MAX_WAIT" ]; then
      echo "  TIMEOUT: $url did not respond after ${MAX_WAIT}s" >&2
      return 1
    fi

    echo "  Waiting ${delay}s for $url (elapsed: ${elapsed}s)..."
    sleep "$delay"
    elapsed=$((elapsed + delay))
    delay=$((delay * 2))
    if [ "$delay" -gt "$MAX_DELAY" ]; then
      delay="$MAX_DELAY"
    fi
  done
}

# Fetch a URL and return the response body; exit 1 if HTTP status != 200.
fetch_json() {
  local url="$1"
  local response http_code body

  # Use a temp file so we can separate body from HTTP status code.
  local tmp
  tmp=$(mktemp)
  http_code=$(curl -sf --max-time 10 -w "%{http_code}" -o "$tmp" "$url" 2>&1 || true)
  body=$(cat "$tmp")
  rm -f "$tmp"

  if [ "$http_code" != "200" ]; then
    echo "  HTTP $http_code from $url" >&2
    echo "  Response body: $body" >&2
    return 1
  fi

  echo "$body"
}

# ── Main ───────────────────────────────────────────────────────────────────

echo ""
echo "ForgeGuard Smoke Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Target: $BASE_URL"
echo ""

# 1. Wait for the service to be reachable.
echo "[1/4] Waiting for service to become reachable..."
if ! wait_for_url "$BASE_URL/health"; then
  echo ""
  echo "RESULT: FAILED — service unreachable after ${MAX_WAIT}s" >&2
  exit 1
fi
log_pass "Service is reachable"

# 2. GET /health → 200, status == "healthy"
echo ""
echo "[2/4] Testing GET /health..."
HEALTH_BODY=$(fetch_json "$BASE_URL/health") || { log_fail "GET /health returned non-200"; }

if [ "$FAIL" -eq 0 ]; then
  HEALTH_STATUS=$(echo "$HEALTH_BODY" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status','MISSING'))" 2>/dev/null || echo "PARSE_ERROR")

  if [ "$HEALTH_STATUS" = "healthy" ]; then
    log_pass "GET /health returned status=healthy"
  else
    log_fail "GET /health status is '$HEALTH_STATUS', expected 'healthy'"
    echo "    Actual response: $HEALTH_BODY" >&2
  fi
fi

# 3. GET /ready → 200, status == "ready"
echo ""
echo "[3/4] Testing GET /ready..."
READY_BODY=$(fetch_json "$BASE_URL/ready") || { log_fail "GET /ready returned non-200"; }

if [ "$FAIL" -eq 0 ]; then
  READY_STATUS=$(echo "$READY_BODY" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status','MISSING'))" 2>/dev/null || echo "PARSE_ERROR")

  if [ "$READY_STATUS" = "ready" ]; then
    log_pass "GET /ready returned status=ready"
  else
    log_fail "GET /ready status is '$READY_STATUS', expected 'ready'"
    echo "    Actual response: $READY_BODY" >&2
  fi
fi

# 4. GET /ready → all dependency checks show "up"
echo ""
echo "[4/4] Verifying all dependency checks are 'up'..."
if [ -n "${READY_BODY:-}" ]; then
  FAILING_CHECKS=$(echo "$READY_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
checks = d.get('checks', {})
failing = [k for k, v in checks.items() if v != 'up']
print(' '.join(failing))
" 2>/dev/null || echo "")

  if [ -z "$FAILING_CHECKS" ]; then
    log_pass "All dependency checks are 'up'"
  else
    log_fail "Dependency checks not 'up': $FAILING_CHECKS"
    echo "    Actual response: $READY_BODY" >&2
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ${PASS} passed, ${FAIL} failed"

if [ "$FAIL" -gt 0 ]; then
  echo "  RESULT: FAILED"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 1
fi

echo "  RESULT: PASSED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
exit 0
