"""Demo remediation recommendation and exception fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

from forgeguard.data.seeds.fixtures.assessments import FINDING_CVE_ID, FINDING_COVERAGE_ID, FINDING_API_DOCS_ID
from forgeguard.data.seeds.fixtures.users import USER_SECURITY_ID, USER_TECHLEAD_ID

# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------
RECOMMENDATION_CVE_ID      = "60000000-0000-0000-0000-000000000001"  # AI-generated
RECOMMENDATION_COVERAGE_ID = "60000000-0000-0000-0000-000000000002"  # template_fallback
EXCEPTION_API_DOCS_ID      = "70000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Remediation Recommendations
# ---------------------------------------------------------------------------
RECOMMENDATIONS = [
    {
        "id": RECOMMENDATION_CVE_ID,
        "finding_id": FINDING_CVE_ID,
        "source": "ai_generated",
        "confidence_score": "0.85",
        "recommendation_text": (
            "Upgrade the cryptography package from version 41.0.0 to 42.0.4 or later. "
            "Run: pip install 'cryptography>=42.0.4'. Update requirements.txt and "
            "requirements-lock.txt. Rebuild the Docker image and push to staging for "
            "verification before production deployment. Verify the fix with "
            "'osv-scanner scan .' — the output should show zero critical CVEs."
        ),
        "implementation_guide": (
            "Step 1: Update requirements.txt: change 'cryptography==41.0.0' to 'cryptography>=42.0.4'.\n"
            "Step 2: Run 'pip install -r requirements.txt' to update the local environment.\n"
            "Step 3: Run the test suite: 'pytest tests/ -v' to confirm no regressions.\n"
            "Step 4: Rebuild the Docker image: 'docker build -t payment-service:patched .'.\n"
            "Step 5: Run osv-scanner: 'osv-scanner scan .' and verify no critical findings.\n"
            "Step 6: Deploy to staging and run smoke tests before promoting to production.\n"
            "Step 7: Create a post-deployment incident report confirming CVE remediation."
        ),
    },
    {
        "id": RECOMMENDATION_COVERAGE_ID,
        "finding_id": FINDING_COVERAGE_ID,
        "source": "template_fallback",
        "confidence_score": "0.95",
        "recommendation_text": (
            "Increase unit test coverage from 45% to meet the 80% threshold. "
            "Focus on the billing.py, webhooks.py, and subscription.py modules which "
            "currently have zero coverage. Use pytest with coverage.py to measure progress: "
            "'pytest --cov=payment --cov-report=html'. "
            "Target: add a minimum of 35 percentage points of coverage within the next sprint."
        ),
        "implementation_guide": None,
    },
]

# ---------------------------------------------------------------------------
# Exception — approved for the API docs finding, expires 2027-01-01
# ---------------------------------------------------------------------------
EXCEPTIONS = [
    {
        "id": EXCEPTION_API_DOCS_ID,
        "finding_id": FINDING_API_DOCS_ID,
        "requested_by": USER_TECHLEAD_ID,
        "justification": (
            "API documentation for /webhooks and /internal/* endpoints is blocked pending "
            "a cross-team API design review scheduled for Q1 2027. The endpoints are "
            "internal-only and not exposed externally. Exception approved until documentation "
            "sprint is completed."
        ),
        "status": "approved",
        "decided_by": USER_SECURITY_ID,
        "decision_comment": (
            "Approved for 6 months. Internal endpoints only — no external exposure confirmed. "
            "Must be completed before Q2 2027 release cycle."
        ),
        "expires_at": datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        "decided_at": datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
    },
]
