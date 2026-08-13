#!/usr/bin/env bash
# integration-test.sh — Validate the ForgeGuard API contract.
#
# Usage:
#   BASE_URL=http://localhost:8000 bash scripts/integration-test.sh
#
# Exit codes:
#   0  All assertions passed
#   1  One or more assertions failed
#
# Tests:
#   /health  — 200, JSON body with status field
#   /ready   — 200, JSON body with status + checks object
#   /metrics — 200, Prometheus text format with expected metric names

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0

# ── Helpers ────────────────────────────────────────────────────────────────

log_pass() { echo "  PASS: $*"; PASS=$((PASS + 1)); }
log_fail() { echo "  FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# Assert HTTP status code equals expected value.
assert_status() {
  local label="$1"
  local actual="$2"
  local expected="$3"
  if [ "$actual" = "$expected" ]; then
    log_pass "$label returned HTTP $expected"
  else
    log_fail "$label returned HTTP $actual, expected $expected"
  fi
}

# Assert a JSON field equals the expected value.
assert_json_field() {
  local label="$1"
  local body="$2"
  local field="$3"
  local expected="$4"
  local actual
  actual=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('$field', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
  if [ "$actual" = "$expected" ]; then
    log_pass "$label.$field == '$expected'"
  else
    log_fail "$label.$field is '$actual', expected '$expected'"
    echo "    Actual response: $body" >&2
  fi
}

# Assert a JSON field exists (non-null, non-missing).
assert_json_field_exists() {
  local label="$1"
  local body="$2"
  local field="$3"
  local actual
  actual=$(echo "$body" | python3 -c "import sys, json; d=json.load(sys.stdin); print('PRESENT' if '$field' in d else 'MISSING')" 2>/dev/null || echo "PARSE_ERROR")
  if [ "$actual" = "PRESENT" ]; then
    log_pass "$label.$field is present"
  else
    log_fail "$label.$field is absent"
    echo "    Actual response: $body" >&2
  fi
}

# Assert the response body contains a given string.
assert_contains() {
  local label="$1"
  local body="$2"
  local pattern="$3"
  if echo "$body" | grep -q "$pattern"; then
    log_pass "$label contains '$pattern'"
  else
    log_fail "$label does not contain '$pattern'"
    echo "    (first 500 chars) ${body:0:500}" >&2
  fi
}

# Fetch URL, store HTTP status and body.
fetch() {
  local url="$1"
  local tmp
  tmp=$(mktemp)
  HTTP_STATUS=$(curl -s --max-time 10 -w "%{http_code}" -o "$tmp" "$url" 2>/dev/null || echo "000")
  RESPONSE_BODY=$(cat "$tmp")
  rm -f "$tmp"
}

# ── Tests ──────────────────────────────────────────────────────────────────

echo ""
echo "ForgeGuard Integration Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Target: $BASE_URL"
echo ""

# Test 1: GET /health
echo "[1/3] GET /health"
fetch "$BASE_URL/health"
assert_status "GET /health" "$HTTP_STATUS" "200"
assert_json_field "GET /health" "$RESPONSE_BODY" "status" "healthy"
assert_json_field_exists "GET /health" "$RESPONSE_BODY" "version"

# Test 2: GET /ready
echo ""
echo "[2/3] GET /ready"
fetch "$BASE_URL/ready"
assert_status "GET /ready" "$HTTP_STATUS" "200"
assert_json_field "GET /ready" "$RESPONSE_BODY" "status" "ready"
assert_json_field_exists "GET /ready" "$RESPONSE_BODY" "checks"

# Validate that the checks object is a dictionary
CHECKS_TYPE=$(echo "$RESPONSE_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
checks = d.get('checks')
print('dict' if isinstance(checks, dict) else type(checks).__name__)
" 2>/dev/null || echo "PARSE_ERROR")

if [ "$CHECKS_TYPE" = "dict" ]; then
  log_pass "GET /ready.checks is an object"
else
  log_fail "GET /ready.checks is '$CHECKS_TYPE', expected object"
  echo "    Actual response: $RESPONSE_BODY" >&2
fi

# Test 3: GET /metrics
echo ""
echo "[3/3] GET /metrics"
fetch "$BASE_URL/metrics"
assert_status "GET /metrics" "$HTTP_STATUS" "200"

# Prometheus text format — assert expected metric name prefixes are present.
assert_contains "GET /metrics" "$RESPONSE_BODY" "forgeguard_"
assert_contains "GET /metrics" "$RESPONSE_BODY" "http_requests"

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
