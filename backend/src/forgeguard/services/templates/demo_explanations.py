"""Template-based fallback explanations and remediation recommendations (WO-056).

Used when the LLM provider is unavailable. Keyed by (rule_type, dimension) then
dimension alone, then a generic fallback.

Each entry has:
    explanation: str  — human-readable explanation of the violation
    recommendation:   str  — recommended action
    implementation_guide: str  — step-by-step guidance
    confidence_score: float  — fixed confidence for template responses
"""

from __future__ import annotations

_TEMPLATE_CONFIDENCE = 0.70

# ---------------------------------------------------------------------------
# Templates keyed by data_key (most specific) or dimension (less specific)
# ---------------------------------------------------------------------------

_BY_DATA_KEY: dict[str, dict[str, str]] = {
    "unit_test_coverage": {
        "explanation": (
            "Unit test coverage is below the required threshold of 80%. "
            "Low coverage means regressions may go undetected in production."
        ),
        "recommendation": "Increase unit test coverage to at least 80%.",
        "implementation_guide": (
            "1. Identify untested modules using pytest-cov: `pytest --cov=src --cov-report=html`.\n"
            "2. Prioritise critical business logic and edge cases.\n"
            "3. Add parameterised tests for data-driven functions.\n"
            "4. Aim for ≥80% line coverage and ≥70% branch coverage."
        ),
    },
    "integration_test_coverage": {
        "explanation": (
            "Integration test coverage is below the required threshold of 60%. "
            "Service interactions and contract boundaries are under-tested."
        ),
        "recommendation": "Increase integration test coverage to at least 60%.",
        "implementation_guide": (
            "1. Map all external service dependencies (databases, APIs, queues).\n"
            "2. Create contract tests for each external dependency.\n"
            "3. Use test containers for database integration tests.\n"
            "4. Run integration tests in CI on every pull request."
        ),
    },
    "mutation_score": {
        "explanation": (
            "The mutation testing score is below 50%, indicating tests do not "
            "adequately catch common code mutations. Tests may be asserting the "
            "wrong things."
        ),
        "recommendation": "Improve test assertion quality to achieve ≥50% mutation score.",
        "implementation_guide": (
            "1. Run mutation testing: `mutmut run --paths-to-mutate=src/`.\n"
            "2. Review surviving mutants — each represents a missing assertion.\n"
            "3. Focus on strengthening assertions rather than adding new tests.\n"
            "4. Eliminate test code that only exercises happy-path scenarios."
        ),
    },
    "dependency_vulnerabilities": {
        "explanation": (
            "One or more third-party dependencies have known security vulnerabilities. "
            "Unpatched vulnerabilities are the leading cause of supply chain attacks."
        ),
        "recommendation": "Remediate all known dependency vulnerabilities immediately.",
        "implementation_guide": (
            "1. Run `pip audit` or `safety check` to enumerate vulnerable packages.\n"
            "2. Upgrade each package to a non-vulnerable version per CVE advisories.\n"
            "3. Where no patch exists, evaluate alternative packages or mitigating controls.\n"
            "4. Add `pip-audit` to your CI pipeline to block new vulnerabilities."
        ),
    },
    "critical_cve_count": {
        "explanation": (
            "Critical CVEs (CVSS ≥9.0) were detected in project dependencies. "
            "Critical vulnerabilities must be treated as P0 incidents."
        ),
        "recommendation": "Patch all critical CVEs before deploying to production.",
        "implementation_guide": (
            "1. Identify critical CVEs: filter `pip audit` output for CVSS ≥9.0.\n"
            "2. Update affected packages immediately — critical CVEs are P0 blockers.\n"
            "3. If no patch is available, implement a WAF rule or isolate the component.\n"
            "4. File a security incident ticket and assign to the security team."
        ),
    },
    "high_cve_count": {
        "explanation": (
            "High-severity CVEs (CVSS 7.0–8.9) were detected, exceeding the allowed limit. "
            "High vulnerabilities significantly increase risk of exploitation."
        ),
        "recommendation": "Reduce high-severity CVEs to two or fewer.",
        "implementation_guide": (
            "1. List all high CVEs with `pip audit --format=json | jq '.[].vulnerabilities[]'`.\n"
            "2. Sort by CVSS score and patch highest first.\n"
            "3. Validate patches in a staging environment before production rollout.\n"
            "4. Schedule remaining remediations within the next sprint."
        ),
    },
    "has_readme": {
        "explanation": (
            "The service lacks a README file. New engineers have no starting point "
            "to understand the service, increasing onboarding time and operational risk."
        ),
        "recommendation": "Create a comprehensive README.md.",
        "implementation_guide": (
            "1. Create README.md in the repository root.\n"
            "2. Include: service overview, setup instructions, environment variables, "
            "API endpoints, testing instructions, and deployment notes.\n"
            "3. Follow the team README template in the developer handbook.\n"
            "4. Require README updates in the PR checklist."
        ),
    },
    "api_docs_complete": {
        "explanation": (
            "API documentation is incomplete. External consumers cannot safely integrate "
            "with this service without accurate endpoint documentation."
        ),
        "recommendation": "Complete OpenAPI/Swagger documentation for all public endpoints.",
        "implementation_guide": (
            "1. Add OpenAPI annotations to all route handlers.\n"
            "2. Document request/response schemas, error codes, and auth requirements.\n"
            "3. Publish the auto-generated docs at /docs and /redoc.\n"
            "4. Validate documentation in CI with `spectral lint openapi.yaml`."
        ),
    },
    "architecture_doc_exists": {
        "explanation": (
            "No architecture documentation exists for this service. Operational teams "
            "cannot diagnose incidents without understanding the system's design."
        ),
        "recommendation": "Create architecture documentation using ADRs or a design doc.",
        "implementation_guide": (
            "1. Create docs/architecture.md describing system components and data flows.\n"
            "2. Include a C4 or sequence diagram for the main request paths.\n"
            "3. Document key architectural decisions as Architecture Decision Records (ADRs).\n"
            "4. Review and update the architecture doc on each significant change."
        ),
    },
    "slo_defined": {
        "explanation": (
            "No Service Level Objectives (SLOs) are defined. Without SLOs, operations "
            "teams cannot set meaningful alerts or prioritise incident response."
        ),
        "recommendation": "Define availability and latency SLOs before production deployment.",
        "implementation_guide": (
            "1. Agree target availability (e.g., 99.9%) with stakeholders.\n"
            "2. Define latency SLOs: p50, p95, p99 for each public endpoint.\n"
            "3. Document SLOs in the service runbook and link from the README.\n"
            "4. Configure alerting to page on SLO breach with a 5-minute error budget burn rate."
        ),
    },
    "monitoring_configured": {
        "explanation": (
            "Monitoring is not configured for this service. Production incidents will "
            "go undetected until customers report them."
        ),
        "recommendation": "Configure observability stack: metrics, logs, and traces.",
        "implementation_guide": (
            "1. Instrument the application with Prometheus metrics (request rate, error rate, latency).\n"
            "2. Configure structured JSON logging with a correlation ID on every request.\n"
            "3. Add distributed tracing with OpenTelemetry.\n"
            "4. Create a Grafana dashboard and wire pagerduty alerts for critical metrics."
        ),
    },
}

# Dimension-level fallbacks used when no data_key match is found
_BY_DIMENSION: dict[str, dict[str, str]] = {
    "code_quality": {
        "explanation": (
            "A code quality policy rule violation was detected. "
            "Code quality issues accumulate as technical debt and increase defect rates."
        ),
        "recommendation": "Review and remediate the identified code quality issue.",
        "implementation_guide": (
            "1. Run static analysis tools (pylint, flake8, or SonarQube) on the codebase.\n"
            "2. Address violations by severity: errors first, then warnings.\n"
            "3. Add pre-commit hooks to prevent regressions.\n"
            "4. Schedule refactoring in the next sprint."
        ),
    },
    "test_coverage": {
        "explanation": (
            "A test coverage policy violation was detected. "
            "Insufficient test coverage increases the risk of undetected regressions."
        ),
        "recommendation": "Increase test coverage to meet the defined threshold.",
        "implementation_guide": (
            "1. Measure current coverage: `pytest --cov=src --cov-report=term-missing`.\n"
            "2. Identify the files furthest from the threshold.\n"
            "3. Add tests for critical paths and edge cases first.\n"
            "4. Enforce the threshold in CI to prevent regressions."
        ),
    },
    "security": {
        "explanation": (
            "A security policy rule violation was detected. "
            "Security violations must be remediated before production deployment."
        ),
        "recommendation": "Remediate the identified security issue immediately.",
        "implementation_guide": (
            "1. Review the evidence field for the specific violation details.\n"
            "2. Consult the security team for guidance on the remediation approach.\n"
            "3. Implement the fix and verify with a security scan.\n"
            "4. File a security incident ticket for tracking and audit purposes."
        ),
    },
    "documentation": {
        "explanation": (
            "A documentation policy rule violation was detected. "
            "Missing documentation increases onboarding time and operational risk."
        ),
        "recommendation": "Create or update the required documentation.",
        "implementation_guide": (
            "1. Identify which documentation artefacts are missing or incomplete.\n"
            "2. Follow the team documentation standards in the developer handbook.\n"
            "3. Add documentation review to the PR checklist.\n"
            "4. Automate documentation generation where possible (e.g., from docstrings)."
        ),
    },
    "operations_readiness": {
        "explanation": (
            "An operations readiness policy rule violation was detected. "
            "Services that are not operationally ready create reliability risks in production."
        ),
        "recommendation": "Complete the identified operations readiness requirement.",
        "implementation_guide": (
            "1. Review the failing rule to understand what operational artefact is missing.\n"
            "2. Create the required artefact (runbook, SLO, on-call rotation, etc.).\n"
            "3. Validate the artefact against the team's operations checklist.\n"
            "4. Update the service metadata to reflect the completed requirement."
        ),
    },
}

_GENERIC_FALLBACK: dict[str, str] = {
    "explanation": (
        "A policy rule violation was detected. "
        "Review the evidence field for details about the specific violation."
    ),
    "recommendation": "Review and remediate the identified policy violation.",
    "implementation_guide": (
        "1. Review the violation evidence in detail.\n"
        "2. Consult the relevant policy documentation for remediation guidance.\n"
        "3. Implement the fix and re-run the governance evaluation to verify.\n"
        "4. Document the remediation in the audit log."
    ),
}


def get_explanation(data_key: str | None, dimension: str | None) -> dict[str, str]:
    """Return the best-match template dict for the given data_key and dimension.

    Lookup order:
        1. data_key exact match
        2. dimension exact match
        3. generic fallback

    Returns a dict with keys: explanation, recommendation, implementation_guide.
    """
    if data_key and data_key in _BY_DATA_KEY:
        return dict(_BY_DATA_KEY[data_key])
    if dimension and dimension in _BY_DIMENSION:
        return dict(_BY_DIMENSION[dimension])
    return dict(_GENERIC_FALLBACK)
