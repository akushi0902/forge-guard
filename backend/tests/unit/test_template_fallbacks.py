"""Unit tests for template_fallbacks module (WO-067).

Verifies all 20 templates:
    - Are registered
    - Render correctly
    - Contain required sections (explanation, impact, remediation)
    - Are clearly labeled as pre-generated responses
"""

from __future__ import annotations

import pytest

from forgeguard.services.agent.template_fallbacks import (
    FallbackTemplate,
    get_all_templates,
    get_supported_finding_types,
    get_template,
)

# The 20 required finding types per AC-7 and the work order spec.
_REQUIRED_TYPES = [
    "LOW_TEST_COVERAGE",
    "OUTDATED_DEPENDENCY",
    "MISSING_README",
    "CRITICAL_CVE",
    "MISSING_HEALTH_CHECK",
    "NO_CI_CD_PIPELINE",
    "WEAK_PASSWORD_POLICY",
    "MISSING_ERROR_HANDLING",
    "NO_MONITORING",
    "INSECURE_DEPENDENCY",
    "MISSING_API_DOCS",
    "NO_CODE_REVIEW",
    "MISSING_RUNBOOK",
    "STALE_BRANCH",
    "NO_RATE_LIMITING",
    "MISSING_INPUT_VALIDATION",
    "NO_BACKUP_STRATEGY",
    "EXCESSIVE_PERMISSIONS",
    "MISSING_CHANGELOG",
    "NO_LOAD_TESTING",
]


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

class TestTemplateCoverage:
    def test_exactly_20_templates_registered(self):
        templates = get_all_templates()
        assert len(templates) == 20

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_required_type_registered(self, finding_type):
        template = get_template(finding_type)
        assert template is not None, f"Template for {finding_type!r} not registered"

    def test_get_supported_finding_types_returns_all(self):
        supported = get_supported_finding_types()
        for ft in _REQUIRED_TYPES:
            assert ft in supported

    def test_unknown_type_returns_none(self):
        assert get_template("NOT_A_REAL_TYPE") is None


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------

class TestTemplateStructure:
    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_has_non_empty_title(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        assert len(t.title.strip()) > 0

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_has_non_empty_explanation(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        assert len(t.explanation.strip()) > 20

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_has_non_empty_impact(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        assert len(t.impact.strip()) > 20

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_has_at_least_three_remediation_steps(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        assert len(t.remediation_steps) >= 3, (
            f"{finding_type} has only {len(t.remediation_steps)} remediation steps"
        )

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_remediation_steps_are_non_empty_strings(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        for step in t.remediation_steps:
            assert isinstance(step, str) and len(step.strip()) > 0

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_confidence_in_range(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        assert 0.0 <= t.confidence <= 1.0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_pre_generated_prefix(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render(service_name="test-service")
        assert "pre-generated response" in rendered.lower()

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_service_name(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render(service_name="my-payment-service")
        assert "my-payment-service" in rendered

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_title(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render()
        assert t.title in rendered

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_numbered_steps(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render()
        assert "1." in rendered

    def test_render_uses_default_service_name(self):
        t = get_template("LOW_TEST_COVERAGE")
        assert t is not None
        rendered = t.render()
        assert "your service" in rendered

    def test_render_returns_string(self):
        t = get_template("CRITICAL_CVE")
        assert t is not None
        result = t.render(service_name="payment-api")
        assert isinstance(result, str)
        assert len(result) > 100

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_what_is_happening_section(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render()
        assert "What's happening" in rendered

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_why_it_matters_section(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render()
        assert "Why it matters" in rendered

    @pytest.mark.parametrize("finding_type", _REQUIRED_TYPES)
    def test_render_contains_how_to_fix_section(self, finding_type):
        t = get_template(finding_type)
        assert t is not None
        rendered = t.render()
        assert "How to fix it" in rendered


# ---------------------------------------------------------------------------
# FallbackTemplate dataclass
# ---------------------------------------------------------------------------

class TestFallbackTemplateDataclass:
    def test_frozen_dataclass(self):
        t = get_template("LOW_TEST_COVERAGE")
        assert t is not None
        with pytest.raises((AttributeError, TypeError)):
            t.title = "overwritten"  # type: ignore[misc]

    def test_finding_type_matches_key(self):
        for ft in _REQUIRED_TYPES:
            t = get_template(ft)
            assert t is not None
            assert t.finding_type == ft
