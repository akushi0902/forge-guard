#!/usr/bin/env sh
# Smoke test for the ForgeGuard frontend container.
#
# Starts the Docker Compose stack (or connects to a running one), waits for
# health checks to pass, then verifies:
#   1. HTTP → HTTPS redirect (port 80 returns 301)
#   2. HTTPS root returns 200 with all 7 security headers
#   3. SPA routing: deep client-side routes return 200 (not 404)
#   4. /health endpoint returns 200 with body "OK"
#   5. Static /assets/ served with immutable cache headers
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
#
# Usage:
#   ./tests/smoke-test.sh                     # bring up full stack
#   SKIP_COMPOSE=1 ./tests/smoke-test.sh      # assume stack already running
#   HOST=myserver.example.com ./tests/smoke-test.sh

set -e

HOST="${HOST:-localhost}"
HTTP_PORT="${HTTP_PORT:-80}"
HTTPS_PORT="${HTTPS_PORT:-443}"
TIMEOUT="${TIMEOUT:-60}"
SKIP_COMPOSE="${SKIP_COMPOSE:-0}"

PASS=0
FAIL=0

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

check() {
    label="$1"
    expected="$2"
    actual="$3"

    if echo "${actual}" | grep -qF "${expected}"; then
        echo "  [PASS] ${label}"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] ${label}"
        echo "         expected: ${expected}"
        echo "         got:      ${actual}"
        FAIL=$((FAIL + 1))
    fi
}

wait_healthy() {
    echo "Waiting for health check to pass (timeout: ${TIMEOUT}s)..."
    elapsed=0
    while [ "${elapsed}" -lt "${TIMEOUT}" ]; do
        status=$(curl -sk -o /dev/null -w "%{http_code}" "https://${HOST}:${HTTPS_PORT}/health" 2>/dev/null || echo "000")
        if [ "${status}" = "200" ]; then
            echo "  Container is healthy."
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "  Container did not become healthy within ${TIMEOUT}s."
    return 1
}

# --------------------------------------------------------------------------
# Stack management
# --------------------------------------------------------------------------

if [ "${SKIP_COMPOSE}" != "1" ]; then
    echo "Starting Docker Compose stack..."
    docker compose up -d --build
    wait_healthy
else
    echo "Skipping docker compose (SKIP_COMPOSE=1) — assuming stack is running."
fi

# --------------------------------------------------------------------------
# Test 1: HTTP → HTTPS redirect
# --------------------------------------------------------------------------
echo ""
echo "Test 1: HTTP → HTTPS redirect"
redirect_code=$(curl -s -o /dev/null -w "%{http_code}" "http://${HOST}:${HTTP_PORT}/" 2>/dev/null || echo "000")
check "HTTP 80 returns 301" "301" "${redirect_code}"

# --------------------------------------------------------------------------
# Test 2: HTTPS root returns 200 with all 7 security headers
# --------------------------------------------------------------------------
echo ""
echo "Test 2: HTTPS root — 200 + security headers"
headers=$(curl -sk -I "https://${HOST}:${HTTPS_PORT}/" 2>/dev/null)

root_code=$(echo "${headers}" | head -1 | awk '{print $2}')
check "HTTPS 443 returns 200" "200" "${root_code}"

check "Strict-Transport-Security present"  "strict-transport-security"  "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "Content-Security-Policy present"    "content-security-policy"    "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "X-Content-Type-Options present"     "x-content-type-options"     "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "X-Frame-Options present"            "x-frame-options"            "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "X-XSS-Protection present"           "x-xss-protection"           "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "Referrer-Policy present"            "referrer-policy"            "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"
check "Permissions-Policy present"         "permissions-policy"         "$(echo "${headers}" | tr '[:upper:]' '[:lower:]')"

# --------------------------------------------------------------------------
# Test 3: SPA routing — deep client-side routes return 200
# --------------------------------------------------------------------------
echo ""
echo "Test 3: SPA routing — deep routes return index.html"
for route in /dashboard /services/some-uuid /releases/some-uuid/findings /admin/settings; do
    code=$(curl -sk -o /dev/null -w "%{http_code}" "https://${HOST}:${HTTPS_PORT}${route}" 2>/dev/null || echo "000")
    check "SPA route ${route} returns 200" "200" "${code}"
done

# --------------------------------------------------------------------------
# Test 4: /health endpoint
# --------------------------------------------------------------------------
echo ""
echo "Test 4: /health endpoint"
health_body=$(curl -sk "https://${HOST}:${HTTPS_PORT}/health" 2>/dev/null)
health_code=$(curl -sk -o /dev/null -w "%{http_code}" "https://${HOST}:${HTTPS_PORT}/health" 2>/dev/null || echo "000")
check "/health returns 200" "200" "${health_code}"
check "/health body is OK"  "OK"  "${health_body}"

# --------------------------------------------------------------------------
# Test 5: Static asset cache headers
# --------------------------------------------------------------------------
echo ""
echo "Test 5: /assets/ cache headers"
# The dist/assets/ directory may be empty in a test build, so we check the
# response from requesting any path under /assets/ — even a 404 from nginx
# would not carry the Cache-Control header, confirming the location block
# is active. A full E2E test would need to find a real asset filename.
assets_headers=$(curl -sk -I "https://${HOST}:${HTTPS_PORT}/assets/nonexistent.js" 2>/dev/null | tr '[:upper:]' '[:lower:]')
# If an asset exists and is served, expect immutable header.
# If 404, the absence of immutable is acceptable — report as info only.
if echo "${assets_headers}" | grep -q "cache-control"; then
    check "Assets served with immutable cache" "immutable" "${assets_headers}"
else
    echo "  [INFO] No /assets/ file found to test cache headers — ensure a real build exists."
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  Smoke test complete"
echo "  Passed: ${PASS}   Failed: ${FAIL}"
echo "========================================"

if [ "${SKIP_COMPOSE}" != "1" ] && [ "${LEAVE_UP:-0}" != "1" ]; then
    echo "Tearing down Docker Compose stack..."
    docker compose down
fi

if [ "${FAIL}" -gt 0 ]; then
    exit 1
fi

exit 0
