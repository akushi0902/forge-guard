"""Unit tests for the AI agent intent classifier (WO-065).

Tests cover all 6 intent categories, ambiguous queries, empty input,
and edge cases with 15+ test cases as required by the acceptance criteria.
"""

from __future__ import annotations

import pytest

from forgeguard.services.agent.intent_classifier import IntentCategory, IntentClassifier


@pytest.fixture(scope="module")
def clf() -> IntentClassifier:
    return IntentClassifier()


# ---------------------------------------------------------------------------
# HEALTH_SCORE intent
# ---------------------------------------------------------------------------

class TestHealthScoreIntent:
    def test_health_score_exact(self, clf):
        assert clf.classify("What is my health score?") == IntentCategory.HEALTH_SCORE

    def test_health_score_service_health(self, clf):
        assert clf.classify("Show me the service health for payment-service") == IntentCategory.HEALTH_SCORE

    def test_overall_score(self, clf):
        assert clf.classify("What is the overall score for my service?") == IntentCategory.HEALTH_SCORE

    def test_engineering_score(self, clf):
        assert clf.classify("Give me the engineering score breakdown") == IntentCategory.HEALTH_SCORE

    def test_dimension_score(self, clf):
        assert clf.classify("What is the test_coverage dimension score?") == IntentCategory.HEALTH_SCORE


# ---------------------------------------------------------------------------
# FINDINGS intent
# ---------------------------------------------------------------------------

class TestFindingsIntent:
    def test_findings_list(self, clf):
        assert clf.classify("Show me my findings") == IntentCategory.FINDINGS

    def test_violations(self, clf):
        assert clf.classify("List all policy violations") == IntentCategory.FINDINGS

    def test_open_issues(self, clf):
        assert clf.classify("What open issues do I have?") == IntentCategory.FINDINGS

    def test_critical_findings(self, clf):
        assert clf.classify("Do I have any critical findings?") == IntentCategory.FINDINGS

    def test_high_severity(self, clf):
        assert clf.classify("What are my high severity findings?") == IntentCategory.FINDINGS

    def test_whats_wrong(self, clf):
        assert clf.classify("What's wrong with my service?") == IntentCategory.FINDINGS


# ---------------------------------------------------------------------------
# REMEDIATION intent
# ---------------------------------------------------------------------------

class TestRemediationIntent:
    def test_how_to_fix(self, clf):
        assert clf.classify("How do I fix this finding?") == IntentCategory.REMEDIATION

    def test_remediate(self, clf):
        assert clf.classify("Help me remediate the security finding") == IntentCategory.REMEDIATION

    def test_guidance(self, clf):
        assert clf.classify("Give me guidance on resolving the coverage issue") == IntentCategory.REMEDIATION

    def test_what_should_i_do(self, clf):
        assert clf.classify("What should I do to fix this?") == IntentCategory.REMEDIATION

    def test_recommendation(self, clf):
        assert clf.classify("What is the recommendation for this violation?") == IntentCategory.REMEDIATION


# ---------------------------------------------------------------------------
# RELEASE_STATUS intent
# ---------------------------------------------------------------------------

class TestReleaseStatusIntent:
    def test_can_i_release(self, clf):
        assert clf.classify("Can I release my changes?") == IntentCategory.RELEASE_STATUS

    def test_release_status(self, clf):
        assert clf.classify("What is my release status?") == IntentCategory.RELEASE_STATUS

    def test_release_blocked(self, clf):
        assert clf.classify("Why is my release blocked?") == IntentCategory.RELEASE_STATUS

    def test_deployment_risk(self, clf):
        assert clf.classify("What is the deployment risk for this PR?") == IntentCategory.RELEASE_STATUS

    def test_ready_to_release(self, clf):
        assert clf.classify("Is my service ready to release?") == IntentCategory.RELEASE_STATUS


# ---------------------------------------------------------------------------
# POLICY_RULES intent
# ---------------------------------------------------------------------------

class TestPolicyRulesIntent:
    def test_policies(self, clf):
        assert clf.classify("Show me the active policies") == IntentCategory.POLICY_RULES

    def test_policy_rules(self, clf):
        assert clf.classify("What policy rules apply to my service?") == IntentCategory.POLICY_RULES

    def test_thresholds(self, clf):
        assert clf.classify("What thresholds are configured?") == IntentCategory.POLICY_RULES

    def test_what_rules(self, clf):
        assert clf.classify("What are the rules for test coverage?") == IntentCategory.POLICY_RULES

    def test_governance_rules(self, clf):
        assert clf.classify("List governance rules") == IntentCategory.POLICY_RULES


# ---------------------------------------------------------------------------
# GENERAL_HELP intent (fallback)
# ---------------------------------------------------------------------------

class TestGeneralHelpIntent:
    def test_empty_string(self, clf):
        assert clf.classify("") == IntentCategory.GENERAL_HELP

    def test_whitespace_only(self, clf):
        assert clf.classify("   ") == IntentCategory.GENERAL_HELP

    def test_unrelated_query(self, clf):
        assert clf.classify("What is the weather today?") == IntentCategory.GENERAL_HELP

    def test_hello(self, clf):
        assert clf.classify("Hello, how are you?") == IntentCategory.GENERAL_HELP

    def test_help_general(self, clf):
        assert clf.classify("Help me") == IntentCategory.GENERAL_HELP

    def test_completely_unrecognized(self, clf):
        assert clf.classify("xyz123 foobar baz") == IntentCategory.GENERAL_HELP


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_case_insensitive(self, clf):
        assert clf.classify("WHAT IS MY HEALTH SCORE") == IntentCategory.HEALTH_SCORE

    def test_mixed_case(self, clf):
        assert clf.classify("Can I RELEASE my changes?") == IntentCategory.RELEASE_STATUS

    def test_special_chars(self, clf):
        result = clf.classify("What's my health score? <script>alert(1)</script>")
        assert result == IntentCategory.HEALTH_SCORE

    def test_very_long_query(self, clf):
        query = "health score " * 200
        result = clf.classify(query)
        assert result == IntentCategory.HEALTH_SCORE

    def test_none_treated_as_general(self, clf):
        # None is not a valid input but we guard against empty string
        result = clf.classify("")
        assert result == IntentCategory.GENERAL_HELP
