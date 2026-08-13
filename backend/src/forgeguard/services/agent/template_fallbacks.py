"""Template fallback system for the AI agent (WO-067).

Provides 20 pre-written, high-quality response templates keyed by finding_type.
Each template covers:
    - Explanation: what the issue is and why it was flagged.
    - Impact: business and engineering consequences.
    - Remediation steps: concrete, actionable steps to resolve the issue.

Templates are clearly labeled with a 'This is a pre-generated response' prefix
per acceptance criteria AC-7.

Usage:
    from forgeguard.services.agent.template_fallbacks import get_template

    template = get_template("LOW_TEST_COVERAGE")
    if template:
        response_text = template.render(service_name="payment-service")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_TEMPLATE_PREFIX = (
    "⚠️ **This is a pre-generated response** — the AI explanation service is "
    "currently unavailable. The guidance below is accurate and actionable but "
    "may not be tailored to your specific service context.\n\n"
)


@dataclass(frozen=True)
class FallbackTemplate:
    """A pre-written response template for a common finding type.

    Attributes:
        finding_type: Finding type key (e.g. "LOW_TEST_COVERAGE").
        title:        Short human-readable title.
        explanation:  What the issue is and why it was flagged.
        impact:       Business and engineering consequences.
        remediation_steps: Ordered list of actionable steps.
        confidence:   Template confidence indicator (0–1). Pre-written templates
                      use 0.7 as a standard value — lower than AI-generated
                      responses (0.85) to signal reduced personalisation.
    """

    finding_type: str
    title: str
    explanation: str
    impact: str
    remediation_steps: list[str]
    confidence: float = 0.7

    def render(self, service_name: str = "your service", **kwargs: Any) -> str:
        """Render the template as a formatted response string.

        Args:
            service_name: Name of the service being discussed.
            **kwargs:     Additional substitution variables (currently unused;
                          reserved for future template enrichment).

        Returns:
            Formatted response string prefixed with the pre-generated banner.
        """
        steps_text = "\n".join(
            f"  {i + 1}. {step}" for i, step in enumerate(self.remediation_steps)
        )
        body = (
            f"## {self.title}\n\n"
            f"**Service:** {service_name}\n\n"
            f"### What's happening?\n{self.explanation}\n\n"
            f"### Why it matters\n{self.impact}\n\n"
            f"### How to fix it\n{steps_text}\n"
        )
        return _TEMPLATE_PREFIX + body


# ---------------------------------------------------------------------------
# Template definitions — 20 most common finding types
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, FallbackTemplate] = {}


def _register(template: FallbackTemplate) -> None:
    _TEMPLATES[template.finding_type] = template


_register(FallbackTemplate(
    finding_type="LOW_TEST_COVERAGE",
    title="Low Test Coverage",
    explanation=(
        "ForgeGuard detected that the test coverage for this service falls below "
        "the configured threshold (typically 80% line coverage). The Policy "
        "Guardian evaluates test coverage data from your CI pipeline and flags "
        "services that are under-tested as a code quality risk."
    ),
    impact=(
        "Low test coverage increases the probability of regressions being "
        "introduced undetected. Release risk scores are elevated, and releases "
        "may be blocked or require additional reviewer approval. Teams with low "
        "coverage take significantly longer to detect and fix production defects."
    ),
    remediation_steps=[
        "Run your test suite with coverage reporting enabled: `pytest --cov=src --cov-report=term-missing`.",
        "Identify uncovered modules in the coverage report — prioritise business-critical paths.",
        "Write unit tests for uncovered functions, focusing on happy path, edge cases, and error conditions.",
        "Add integration tests for API endpoints and database interactions.",
        "Configure a coverage gate in your CI pipeline (e.g. `--cov-fail-under=80`) to prevent regression.",
        "Aim for at least 80% line coverage; target 90%+ for security-sensitive modules.",
        "Re-trigger a ForgeGuard assessment after improving coverage to update your Health Score.",
    ],
))

_register(FallbackTemplate(
    finding_type="OUTDATED_DEPENDENCY",
    title="Outdated Dependency Detected",
    explanation=(
        "One or more of your service's dependencies are significantly out of date "
        "relative to the latest stable release. ForgeGuard scans dependency "
        "manifests (package.json, requirements.txt, pom.xml, etc.) and flags "
        "packages that are more than two major versions behind or have known "
        "security patches available."
    ),
    impact=(
        "Outdated dependencies frequently contain unpatched security vulnerabilities "
        "(CVEs). They also accumulate breaking changes that make future upgrades "
        "increasingly costly. Services with stale dependencies receive lower "
        "security and operations readiness dimension scores."
    ),
    remediation_steps=[
        "Run a dependency audit: `npm audit` / `pip-audit` / `mvn dependency:analyze`.",
        "Review the list of outdated packages and prioritise those with CVEs first.",
        "Update high-severity CVE packages immediately; test thoroughly before deploying.",
        "Schedule a regular dependency update cadence (e.g. weekly automated PRs via Dependabot).",
        "Pin transitive dependency versions in your lock file to ensure reproducible builds.",
        "Add a CI step to fail builds when new critical CVEs are detected in dependencies.",
        "Retrigger a ForgeGuard assessment to verify the finding is resolved.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_README",
    title="Missing or Inadequate README",
    explanation=(
        "ForgeGuard's documentation policy rule requires all services to have a "
        "README that covers: service purpose, setup instructions, configuration "
        "options, and a link to the runbook. This service's README is either "
        "absent or does not meet the minimum content requirements."
    ),
    impact=(
        "Poor documentation increases onboarding time for new engineers and makes "
        "incident response slower. It contributes to a lower Documentation "
        "dimension score, which reduces the overall Health Score and can block "
        "releases requiring Tech Lead approval."
    ),
    remediation_steps=[
        "Create or update README.md at the repository root.",
        "Include: service overview (1–2 paragraphs), architecture diagram or link.",
        "Add setup instructions: prerequisites, local environment setup, how to run tests.",
        "Document configuration: list all environment variables with descriptions and defaults.",
        "Link to the operations runbook (create one if it doesn't exist).",
        "Add a 'Contributing' section with PR and code review guidelines.",
        "Commit the README and re-run the ForgeGuard assessment to resolve the finding.",
    ],
))

_register(FallbackTemplate(
    finding_type="CRITICAL_CVE",
    title="Critical CVE in Dependency",
    explanation=(
        "A critical Common Vulnerabilities and Exposures (CVE) entry has been "
        "detected in one or more of this service's dependencies. Critical CVEs "
        "(CVSS score ≥ 9.0) represent severe security vulnerabilities that can "
        "lead to remote code execution, data exfiltration, or full service "
        "compromise if exploited."
    ),
    impact=(
        "Critical CVEs trigger automatic escalation to the Security Reviewer role "
        "and result in an automatic BLOCK decision for release assessments "
        "regardless of the Health Score. Unpatched critical CVEs represent "
        "immediate organisational risk and regulatory compliance exposure."
    ),
    remediation_steps=[
        "Identify the exact CVE: check the finding details for the CVE identifier (e.g. CVE-2023-XXXXX).",
        "Check the National Vulnerability Database (nvd.nist.gov) for patch availability.",
        "Update the affected dependency to the patched version immediately.",
        "If no patch is available: assess whether a workaround exists (disable vulnerable feature, network isolation).",
        "Run a full security scan after patching: `trivy image your-service:latest`.",
        "Document the remediation in your audit trail and notify your Security Reviewer.",
        "Re-submit a release assessment after patching to clear the BLOCK decision.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_HEALTH_CHECK",
    title="Missing Service Health Check Endpoint",
    explanation=(
        "ForgeGuard's operations readiness policy requires services to expose a "
        "health check endpoint (typically /health or /healthz) that returns HTTP "
        "200 when the service is healthy. This service does not expose a "
        "compliant health endpoint detectable by the platform."
    ),
    impact=(
        "Without a health check endpoint, load balancers and orchestration "
        "platforms (Kubernetes, ECS) cannot detect unhealthy service instances, "
        "leading to traffic being routed to degraded instances. It also reduces "
        "the Operations Readiness dimension score."
    ),
    remediation_steps=[
        "Implement a GET /health endpoint that returns: `{\"status\": \"healthy\", \"version\": \"x.x.x\"}`.",
        "The endpoint must return HTTP 200 when healthy and HTTP 503 when degraded.",
        "Include dependency checks (database connectivity, downstream services) in the health response.",
        "Add a liveness probe and readiness probe in your Kubernetes manifest or ECS task definition.",
        "Test the endpoint locally: `curl -f http://localhost:8000/health`.",
        "Configure your load balancer's health check to target this endpoint.",
        "Re-run the ForgeGuard assessment to verify the health endpoint is detected.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_CI_CD_PIPELINE",
    title="Missing CI/CD Pipeline Configuration",
    explanation=(
        "ForgeGuard detected that this service repository does not contain a CI/CD "
        "pipeline configuration file (e.g. .github/workflows/, Jenkinsfile, "
        ".gitlab-ci.yml, forge-shipping.yml). All services under governance must "
        "have automated build, test, and deployment pipelines."
    ),
    impact=(
        "Without a CI/CD pipeline, code changes are deployed manually — increasing "
        "human error risk and slowing delivery. It also means automated quality "
        "gates (test coverage, security scans) are not enforced, leading to lower "
        "scores across multiple dimensions."
    ),
    remediation_steps=[
        "Choose a CI/CD platform: GitHub Actions, GitLab CI, Jenkins, or Forge Shipping.",
        "Create a pipeline configuration that runs: lint → test → build → security scan → deploy.",
        "Add a test step with coverage reporting and a minimum coverage gate.",
        "Add a dependency vulnerability scan step (Trivy, Snyk, or OWASP Dependency Check).",
        "Configure environment-specific deployment gates (dev → staging → production).",
        "Add the ForgeGuard webhook notification step to trigger re-assessment on deploy.",
        "Commit the pipeline config and verify a successful pipeline run.",
    ],
))

_register(FallbackTemplate(
    finding_type="WEAK_PASSWORD_POLICY",
    title="Weak Password Policy Configuration",
    explanation=(
        "ForgeGuard detected that the service's authentication configuration does "
        "not enforce a sufficient password policy. Requirements include: minimum "
        "12 characters, at least one uppercase, one lowercase, one digit, and one "
        "special character, plus bcrypt hashing with a cost factor of at least 12."
    ),
    impact=(
        "Weak password policies make accounts vulnerable to brute-force and "
        "dictionary attacks. This is an OWASP A07 (Authentication Failures) "
        "violation and directly impacts the Security dimension score. Services "
        "with weak authentication policies may be blocked from release."
    ),
    remediation_steps=[
        "Update the password validation regex to enforce: 12+ chars, uppercase, lowercase, digit, special char.",
        "Migrate password hashing to bcrypt with cost factor 12: `bcrypt.hashpw(pw, bcrypt.gensalt(12))`.",
        "Implement account lockout after 5 consecutive failed login attempts within 15 minutes.",
        "Add exponential backoff on repeated failed login attempts.",
        "Enforce password change on first login and when compromised credentials are detected.",
        "Consider integrating with HaveIBeenPwned API to reject known compromised passwords.",
        "Document the password policy in your service's security documentation.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_ERROR_HANDLING",
    title="Insufficient Error Handling",
    explanation=(
        "ForgeGuard's code quality rules require services to handle errors "
        "explicitly at API boundaries and return structured error responses. "
        "This service has been detected returning unhandled exceptions directly "
        "to clients (500 errors with stack traces) or silently swallowing errors "
        "without logging."
    ),
    impact=(
        "Poor error handling leaks internal implementation details (stack traces, "
        "file paths, SQL queries) to clients — an OWASP A05 security risk. It "
        "also makes debugging incidents significantly harder and reduces service "
        "reliability scores."
    ),
    remediation_steps=[
        "Wrap all API handlers in a global exception handler that returns structured error responses.",
        "Return errors as: `{\"error\": \"message\", \"code\": \"ERROR_CODE\", \"request_id\": \"...\"}`.",
        "Never expose stack traces, SQL queries, or file paths in API responses.",
        "Log all unexpected exceptions with structured context: request ID, user ID, endpoint.",
        "Distinguish between client errors (4xx) and server errors (5xx) in your error taxonomy.",
        "Add circuit breakers for downstream service calls to prevent cascading failures.",
        "Test error paths explicitly in your test suite — not just the happy path.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_MONITORING",
    title="Missing Observability / Monitoring Configuration",
    explanation=(
        "ForgeGuard's operations readiness policy requires services to expose "
        "metrics in a standard format (Prometheus /metrics, Datadog DogStatsD, "
        "or equivalent) and have alert rules configured for critical service "
        "signals (error rate, latency, availability)."
    ),
    impact=(
        "Services without monitoring are operationally blind. When incidents occur, "
        "teams cannot detect degradation quickly, leading to extended MTTR. The "
        "Operations Readiness dimension score is significantly penalised for "
        "missing observability infrastructure."
    ),
    remediation_steps=[
        "Add a /metrics endpoint exposing Prometheus-format metrics.",
        "Instrument key signals: request rate, error rate, p50/p95/p99 latency, saturation.",
        "Configure alerting rules for: error rate > 1%, p95 latency > 500ms, availability < 99.9%.",
        "Set up a dashboard with the four golden signals (latency, traffic, errors, saturation).",
        "Add distributed tracing with correlation IDs on all requests.",
        "Configure PagerDuty or equivalent for on-call routing.",
        "Add structured logging with log aggregation to a centralised platform (e.g. ELK, Splunk).",
    ],
))

_register(FallbackTemplate(
    finding_type="INSECURE_DEPENDENCY",
    title="Insecure Dependency Configuration",
    explanation=(
        "ForgeGuard detected a dependency with a known security vulnerability "
        "(CVSS score 4.0–8.9, moderate to high severity). While not as urgent as "
        "critical CVEs, high and medium severity vulnerabilities should be patched "
        "within the standard SLA (high: 30 days, medium: 90 days)."
    ),
    impact=(
        "Unpatched insecure dependencies accumulate and collectively represent a "
        "significant attack surface. They lower the Security dimension score and "
        "may elevate the Release Risk Score for changes touching affected packages."
    ),
    remediation_steps=[
        "Run `npm audit` / `pip-audit` / `mvn dependency:check` to get a full vulnerability report.",
        "Sort findings by CVSS score and patch critical/high severity first.",
        "Update each vulnerable package to the minimum patched version.",
        "Review changelogs for breaking changes before upgrading.",
        "Run your full test suite after each dependency update.",
        "If a direct upgrade is not possible, check for a fork, backport, or vendor patch.",
        "Set up automated dependency update PRs (Dependabot, Renovate) to prevent future accumulation.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_API_DOCS",
    title="Missing API Documentation",
    explanation=(
        "ForgeGuard's documentation policy requires all services with REST or "
        "gRPC APIs to expose an OpenAPI (Swagger) specification or equivalent "
        "machine-readable API contract. This service does not expose a /docs, "
        "/openapi.json, or equivalent documentation endpoint."
    ),
    impact=(
        "Missing API documentation slows integration work for other teams, "
        "increases the probability of incorrect API usage, and complicates "
        "security review. It reduces the Documentation dimension score."
    ),
    remediation_steps=[
        "For FastAPI services: API docs are auto-generated — ensure /docs and /openapi.json are enabled.",
        "For other frameworks: integrate Swagger UI (springdoc-openapi, flask-restx, etc.).",
        "Document all endpoints: path, method, request/response schemas, authentication requirements.",
        "Add example request/response payloads to your OpenAPI spec.",
        "Document error responses: all 4xx and 5xx codes with their meaning.",
        "Version your API spec and publish it to your internal developer portal.",
        "Consider generating a client SDK from your OpenAPI spec for strongly-typed integration.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_CODE_REVIEW",
    title="No Code Review Process Enforced",
    explanation=(
        "ForgeGuard detected that this service's repository does not enforce "
        "pull request review requirements. The code quality policy requires at "
        "least one reviewer approval before merging to the main branch, with "
        "additional security reviewer approval for security-sensitive changes."
    ),
    impact=(
        "Without mandatory code review, defects, security vulnerabilities, and "
        "architectural inconsistencies are more likely to reach production. Code "
        "review is a fundamental engineering quality control that impacts Code "
        "Quality and Security dimension scores."
    ),
    remediation_steps=[
        "Enable branch protection on main/master: require at least 1 approved review before merge.",
        "Enable 'Dismiss stale reviews when new commits are pushed'.",
        "Configure CODEOWNERS to automatically assign domain experts as reviewers.",
        "Require security team review for changes to authentication, authorisation, or cryptography modules.",
        "Enable 'Require status checks to pass' so CI must be green before merge.",
        "Document the code review checklist (security, tests, docs, error handling).",
        "Enforce commit signing for auditability.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_RUNBOOK",
    title="Missing Operational Runbook",
    explanation=(
        "ForgeGuard's operations readiness policy requires each service to have "
        "an up-to-date operational runbook covering common failure scenarios, "
        "escalation paths, and recovery procedures. No runbook link was detected "
        "in the service's documentation."
    ),
    impact=(
        "During incidents, teams without a runbook take significantly longer to "
        "diagnose and recover from failures. This is a key contributor to higher "
        "MTTR (Mean Time To Restore) and impacts the Operations Readiness "
        "dimension score."
    ),
    remediation_steps=[
        "Create a runbook document in your team's wiki or docs repository.",
        "Cover: service overview, architecture diagram, dependencies, and SLAs.",
        "Document common failure modes and their diagnostic steps.",
        "Include runbook entries for: high error rate, database connection failure, memory pressure.",
        "Add escalation paths: who to contact for each type of incident.",
        "Document deployment and rollback procedures.",
        "Add the runbook link to your README and alert templates.",
        "Review and update the runbook after each significant incident.",
    ],
))

_register(FallbackTemplate(
    finding_type="STALE_BRANCH",
    title="Stale Long-Running Branch Detected",
    explanation=(
        "ForgeGuard detected a long-running branch that has diverged significantly "
        "from the main branch (typically >30 days old or >100 commits behind). "
        "Stale branches accumulate merge conflicts, become difficult to integrate, "
        "and may contain outdated dependencies or unpatched vulnerabilities."
    ),
    impact=(
        "Stale branches delay delivery, accumulate merge risk, and may contain "
        "security vulnerabilities that have been patched in main but not "
        "backported to the branch. They negatively impact the Code Quality "
        "dimension score."
    ),
    remediation_steps=[
        "Review the stale branch: determine if it is still needed.",
        "If the work is obsolete, close the branch and archive or delete it.",
        "If the branch is still active: rebase it onto the current main branch.",
        "Resolve merge conflicts carefully — pay attention to security-related changes.",
        "Run the full test suite after rebasing to verify correctness.",
        "Establish a team policy: branches older than 2 weeks must be rebased or closed.",
        "Use feature flags to merge incomplete work into main incrementally rather than long-lived branches.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_RATE_LIMITING",
    title="Missing API Rate Limiting",
    explanation=(
        "ForgeGuard's security policy requires all externally-accessible API "
        "endpoints to implement rate limiting to prevent abuse, brute-force "
        "attacks, and denial-of-service conditions. No rate limiting middleware "
        "was detected in this service's configuration."
    ),
    impact=(
        "Without rate limiting, your API is vulnerable to brute-force login "
        "attacks, credential stuffing, and denial-of-service via excessive "
        "requests. This is an OWASP A04 (Insecure Design) violation that "
        "significantly impacts the Security dimension score."
    ),
    remediation_steps=[
        "Implement token-bucket rate limiting at the API gateway or application layer.",
        "Apply limits per IP and per authenticated user: 100 req/min for general endpoints.",
        "Apply stricter limits for authentication endpoints: 10 req/min per IP.",
        "Return HTTP 429 with a Retry-After header when the limit is exceeded.",
        "Log rate limit violations for security monitoring.",
        "Consider distributed rate limiting (Redis-backed) for multi-instance deployments.",
        "Add rate limit bypass for internal service-to-service calls using a service account token.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_INPUT_VALIDATION",
    title="Insufficient Input Validation",
    explanation=(
        "ForgeGuard detected that one or more API endpoints or data processing "
        "paths in this service do not perform adequate input validation. "
        "All external inputs must be validated for type, length, format, and "
        "allowed values before processing."
    ),
    impact=(
        "Missing input validation is the root cause of injection attacks (SQL, "
        "NoSQL, command, LDAP injection), OWASP A03. It can lead to data "
        "corruption, privilege escalation, and remote code execution. It "
        "critically impacts the Security dimension score."
    ),
    remediation_steps=[
        "Adopt a validation library: Pydantic (Python), Joi (Node.js), Bean Validation (Java).",
        "Validate all inputs at the API boundary: type, required/optional, min/max length, regex.",
        "Reject requests with invalid inputs immediately — return 400 with field-level error details.",
        "Never trust user-supplied data for file paths, SQL queries, or system commands.",
        "Use parameterised queries (not string interpolation) for all database interactions.",
        "Add integration tests that verify invalid inputs are rejected with appropriate 400 errors.",
        "Enable strict mode in your validation framework to reject unknown fields by default.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_BACKUP_STRATEGY",
    title="Missing Data Backup Strategy",
    explanation=(
        "ForgeGuard's operations readiness policy requires services that own "
        "persistent data to have a documented and tested backup strategy. No "
        "backup configuration, schedule, or recovery procedure was detected for "
        "this service's data stores."
    ),
    impact=(
        "Without a backup strategy, data loss from hardware failure, accidental "
        "deletion, or ransomware attacks cannot be recovered. This is a critical "
        "operations gap that impacts the Operations Readiness dimension score "
        "and may violate data retention compliance requirements."
    ),
    remediation_steps=[
        "Define your Recovery Point Objective (RPO) and Recovery Time Objective (RTO).",
        "Implement automated daily database backups with a retention period matching your RPO.",
        "Store backups in a separate region or cloud account from primary data.",
        "Enable point-in-time recovery for critical databases (PostgreSQL WAL archiving, RDS PITR).",
        "Test backup restoration quarterly — an untested backup is not a backup.",
        "Document the restore procedure in your runbook.",
        "Encrypt backups at rest and audit access to backup storage.",
    ],
))

_register(FallbackTemplate(
    finding_type="EXCESSIVE_PERMISSIONS",
    title="Excessive Service Account Permissions",
    explanation=(
        "ForgeGuard's security policy applies the principle of least privilege "
        "to service accounts and IAM roles. This service's service account or "
        "database role has been granted more permissions than required for its "
        "documented functionality (e.g. wildcard IAM policies, database superuser "
        "access, or broad cloud resource permissions)."
    ),
    impact=(
        "Excessive permissions amplify the blast radius of a credential compromise. "
        "If the service is exploited, the attacker gains all the permissions "
        "assigned to the service account. This is an OWASP A01 (Broken Access "
        "Control) violation and critically impacts the Security dimension score."
    ),
    remediation_steps=[
        "Audit the service's current IAM / database permissions against actual usage.",
        "Remove all permissions that are not required for the service's documented functionality.",
        "Replace wildcard IAM actions (`*`) with specific, narrowly-scoped actions.",
        "Create a dedicated service account with only the permissions the service needs.",
        "Apply the database principle of least privilege: grant only SELECT/INSERT/UPDATE/DELETE on specific tables.",
        "Rotate service account credentials after reducing permissions.",
        "Add permission boundary policies to prevent privilege escalation.",
        "Review service account permissions quarterly.",
    ],
))

_register(FallbackTemplate(
    finding_type="MISSING_CHANGELOG",
    title="Missing CHANGELOG",
    explanation=(
        "ForgeGuard's documentation policy requires services to maintain a "
        "CHANGELOG (e.g. CHANGELOG.md following Keep a Changelog format) that "
        "records significant changes, bug fixes, and breaking changes for each "
        "release. No CHANGELOG was detected in this repository."
    ),
    impact=(
        "A missing CHANGELOG makes it difficult for dependent teams to understand "
        "what changed between releases, increasing integration risk and slowing "
        "release review. It contributes to a lower Documentation dimension score."
    ),
    remediation_steps=[
        "Create CHANGELOG.md at the repository root following keepachangelog.com conventions.",
        "Structure entries by version with sections: Added, Changed, Deprecated, Removed, Fixed, Security.",
        "Include the current version entry with all changes since the last release.",
        "Backfill the last 3–5 releases with brief summaries.",
        "Add a CI check that validates the CHANGELOG is updated when version is bumped.",
        "Consider automating CHANGELOG generation from conventional commit messages.",
        "Link to the CHANGELOG from your README.",
    ],
))

_register(FallbackTemplate(
    finding_type="NO_LOAD_TESTING",
    title="No Load Testing Evidence",
    explanation=(
        "ForgeGuard's operations readiness policy requires services handling "
        "significant traffic to demonstrate load testing results before release. "
        "No load testing configuration or results were detected in the service's "
        "CI pipeline or documentation."
    ),
    impact=(
        "Untested services may fail under production load, leading to service "
        "degradation or outages. Without load testing data, the release guardian "
        "cannot validate that the service meets its SLA under expected peak traffic. "
        "This impacts the Operations Readiness dimension score."
    ),
    remediation_steps=[
        "Define your service's traffic profile: expected RPS at normal and peak load.",
        "Choose a load testing tool: k6, Locust, Gatling, or Apache JMeter.",
        "Write a load test that simulates realistic user journeys, not just single endpoints.",
        "Run load tests to: 2x expected peak traffic for 30 minutes.",
        "Validate: p95 latency ≤ SLA threshold, error rate < 0.1%, no memory leaks.",
        "Add load test results to your release documentation.",
        "Integrate load tests into your staging deployment pipeline.",
        "Re-run load tests after significant architectural changes.",
    ],
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_template(finding_type: str) -> FallbackTemplate | None:
    """Return the fallback template for *finding_type*, or None if not found.

    Args:
        finding_type: Finding type string (case-sensitive, e.g. "LOW_TEST_COVERAGE").

    Returns:
        FallbackTemplate instance, or None if the type is not covered.
    """
    return _TEMPLATES.get(finding_type)


def get_all_templates() -> dict[str, FallbackTemplate]:
    """Return all registered templates keyed by finding_type."""
    return dict(_TEMPLATES)


def get_supported_finding_types() -> list[str]:
    """Return a sorted list of all finding types with template coverage."""
    return sorted(_TEMPLATES.keys())
