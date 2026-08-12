# Violations Catalog — Payment Service Demo

**WO-055 | ForgeGuard Platform | Last updated: 2026-08-12**

This catalog documents all 10 policy violation scenarios seeded for the Payment
Service demo.  Each scenario lists the rule definition, the simulated value that
causes a failure, and a safety justification for security-dimension violations.

---

## Governance Dimensions Covered

All five dimensions are represented: **code_quality**, **test_coverage**,
**security**, **documentation**, **operations_readiness**.

---

## Severity Distribution

| Severity | Count | Rule Names |
|----------|-------|------------|
| critical | 2 | Critical Path Coverage, Dependency Vulnerability Check |
| high     | 4 | Cyclomatic Complexity, Minimum Coverage, Input Validation Coverage, Health Check Endpoint |
| medium   | 3 | Code Duplication, API Documentation Completeness, Structured Logging Enabled |
| low      | 1 | README Completeness |

---

## Rule Details

### 1. Cyclomatic Complexity Threshold

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000001` |
| Dimension | `code_quality` |
| Severity | **high** |
| Rule type | `threshold_lte` |
| Threshold | max 10 |
| Simulated actual | 15 |
| Weight | 2.0 |
| Finding title | "Cyclomatic complexity score 15 exceeds maximum of 10" |

**Description:** Measures the maximum cyclomatic complexity of any single module
in the Payment Service codebase.  A score above 10 indicates overly complex
branching logic that is hard to test and maintain.

---

### 2. Code Duplication Percentage

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000002` |
| Dimension | `code_quality` |
| Severity | **medium** |
| Rule type | `threshold_lte` |
| Threshold | max 5% |
| Simulated actual | 12.0% |
| Weight | 1.5 |
| Finding title | "Code duplication at 12% — 7pp above the 5% threshold" |

**Description:** Percentage of code blocks flagged as duplicated by a static
analysis tool (e.g. PMD CPD).  High duplication increases maintenance cost.

---

### 3. Minimum Coverage Percentage

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000003` |
| Dimension | `test_coverage` |
| Severity | **high** |
| Rule type | `threshold_gte` |
| Threshold | min 80% |
| Simulated actual | 45.0% |
| Weight | 2.5 |
| Finding title | "Unit test coverage at 45% — 35pp below the 80% minimum" |

**Description:** Overall unit test line coverage as measured by `coverage.py`.
Coverage below 80% significantly increases regression risk.

---

### 4. Critical Path Coverage

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000004` |
| Dimension | `test_coverage` |
| Severity | **critical** |
| Rule type | `threshold_gte` |
| Threshold | min 95% |
| Simulated actual | 60.0% |
| Weight | 3.0 |
| Finding title | "Critical path coverage at 60% — 35pp below the 95% requirement" |

**Description:** Coverage specifically of the payment processing and
authentication code paths.  These are PCI-scope paths that require near-complete
coverage to satisfy compliance obligations.

---

### 5. Dependency Vulnerability Check

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000005` |
| Dimension | `security` |
| Severity | **critical** |
| Rule type | `threshold_eq` |
| Threshold | 0 critical CVEs |
| Simulated actual | 2 |
| Weight | 3.0 |
| Finding title | "2 critical CVEs detected in production dependency tree" |

**Safety Verification:** ✅ SAFE SIMULATION
- The value `2` is a **count** returned by a dependency scanner (e.g. OSV).
- No CVE identifiers, package names, versions, or exploit details are stored.
- The simulated data does not describe any real vulnerability or attack vector.
- This finding demonstrates the governance escalation path only.

---

### 6. Input Validation Coverage

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000006` |
| Dimension | `security` |
| Severity | **high** |
| Rule type | `threshold_gte` |
| Threshold | 100% |
| Simulated actual | 70.0% |
| Weight | 2.5 |
| Finding title | "Input validation covers only 70% of API endpoint groups" |

**Safety Verification:** ✅ SAFE SIMULATION
- The value `70.0` is a **coverage percentage** measured by a static analysis tool.
- It describes the proportion of endpoint groups that have input validation
  decorators or middleware — not an indication of any specific exploitable gap.
- The underlying demo code uses parameterised queries and Pydantic models
  throughout; no injection vulnerability exists.

---

### 7. API Documentation Completeness

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000007` |
| Dimension | `documentation` |
| Severity | **medium** |
| Rule type | `threshold_gte` |
| Threshold | min 90% |
| Simulated actual | 40.0% |
| Weight | 1.0 |
| Finding title | "API documentation covers only 40% of endpoints" |

**Description:** Percentage of API endpoints with a complete OpenAPI/Swagger
specification (description, request schema, response codes).

---

### 8. README Completeness

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000008` |
| Dimension | `documentation` |
| Severity | **low** |
| Rule type | `threshold_eq` |
| Threshold | 1 (required sections present) |
| Simulated actual | 0 (missing sections) |
| Weight | 0.5 |
| Finding title | "README is missing: API reference, runbook link, setup guide" |

**Description:** Boolean check that the README contains the required sections:
overview, setup guide, API reference, and runbook link.

---

### 9. Health Check Endpoint

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000009` |
| Dimension | `operations_readiness` |
| Severity | **high** |
| Rule type | `threshold_eq` |
| Threshold | 1 (endpoint present) |
| Simulated actual | 0 (missing) |
| Weight | 2.0 |
| Finding title | "No /health or /ready endpoint present — Kubernetes probes will fail" |

**Description:** Verifies that the service exposes `/health` and `/ready`
endpoints for Kubernetes liveness and readiness probes.

---

### 10. Structured Logging Enabled

| Field | Value |
|-------|-------|
| Rule ID | `c0000000-0000-0000-0000-000000000010` |
| Dimension | `operations_readiness` |
| Severity | **medium** |
| Rule type | `threshold_eq` |
| Threshold | 1 (fully enabled) |
| Simulated actual | 0 (partial — some modules use `print()`) |
| Weight | 1.0 |
| Finding title | "Structured logging is partial — some modules use unstructured print()" |

**Description:** Verifies that all service modules emit structured JSON logs
with correlation IDs for distributed tracing.

---

## Safety Review Summary

**Reviewer:** ForgeGuard Platform Engineering  
**Review date:** 2026-08-12  
**Outcome:** All security-dimension violations are SAFE SIMULATIONS.

### Security Review Checklist

| Check | Status | Notes |
|-------|--------|-------|
| No actual CVE IDs or package names in seed data | ✅ PASS | Only a count value (integer 2) is stored |
| No exploit code, payloads, or PoC patterns | ✅ PASS | No executable content anywhere in seed data |
| No real credentials, tokens, or secrets | ✅ PASS | All values are synthetic metrics |
| Input validation gap is descriptive only | ✅ PASS | Demo app uses parameterised queries; no real gap exists |
| Seed data cannot be used to identify live vulnerabilities | ✅ PASS | All values are fictional |

No security-dimension violation in this catalog contains genuinely exploitable
content.  The violations demonstrate governance workflow (detection → escalation
→ exception → resolution) without introducing real risk.
