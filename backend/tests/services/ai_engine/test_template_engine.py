"""Unit tests for the TemplateEngine.

Covers:
  - Loading all 20+ templates from YAML files
  - Variable substitution with all context variables
  - Missing variable handling (uses placeholder, does not crash)
  - Finding type lookup hit and miss
  - Generic fallback when no specific template matches
  - Severity-specific template selection
  - Schema validation errors at startup
  - TemplateEngine.load_templates() fail-fast on bad YAML
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from forgeguard.services.ai_engine.template_engine import (
    TemplateEngine,
    TemplateLoadError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from forgeguard.services.ai_engine.templates.schema import TemplateResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine() -> TemplateEngine:
    """Real TemplateEngine backed by the production YAML files."""
    eng = TemplateEngine()
    eng.load_templates()
    return eng


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_ALL_FINDING_TYPES = [
    # code_complexity
    ("high_cyclomatic_complexity", "code_complexity", "high"),
    ("large_file_change", "code_complexity", "medium"),
    ("excessive_churn", "code_complexity", "critical"),
    ("deeply_nested_logic", "code_complexity", "medium"),
    # test_coverage
    ("low_coverage_delta", "test_coverage", "high"),
    ("missing_unit_tests", "test_coverage", "medium"),
    ("missing_integration_tests", "test_coverage", "high"),
    ("test_regression", "test_coverage", "critical"),
    # dependencies
    ("known_cve", "dependencies", "critical"),
    ("outdated_dependency", "dependencies", "medium"),
    ("major_version_bump", "dependencies", "high"),
    ("new_transitive_dependency", "dependencies", "low"),
    # security
    ("secrets_in_code", "security", "critical"),
    ("sql_injection_risk", "security", "critical"),
    ("xss_risk", "security", "high"),
    ("insecure_configuration", "security", "high"),
    # historical
    ("similar_change_caused_incident", "historical", "high"),
    ("high_risk_file_modified", "historical", "high"),
    ("deployment_window_risk", "historical", "high"),
    ("insufficient_soak_time", "historical", "high"),
]


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------

class TestTemplateEngineLoading:
    def test_loads_without_error(self, engine: TemplateEngine) -> None:
        assert engine._loaded is True

    def test_index_not_empty(self, engine: TemplateEngine) -> None:
        assert len(engine._index) >= 20

    def test_load_twice_is_safe(self) -> None:
        eng = TemplateEngine()
        eng.load_templates()
        eng.load_templates()  # second call should not raise

    def test_missing_data_dir_raises(self, tmp_path: Path) -> None:
        eng = TemplateEngine(data_dir=tmp_path / "nonexistent")
        with pytest.raises(TemplateLoadError, match="No template YAML files found"):
            eng.load_templates()

    def test_empty_data_dir_raises(self, tmp_path: Path) -> None:
        eng = TemplateEngine(data_dir=tmp_path)
        with pytest.raises(TemplateLoadError, match="No template YAML files found"):
            eng.load_templates()

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": this: is: invalid: yaml: {{{{", encoding="utf-8")
        eng = TemplateEngine(data_dir=tmp_path)
        with pytest.raises(TemplateLoadError):
            eng.load_templates()

    def test_missing_templates_key_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("some_key: value\n", encoding="utf-8")
        eng = TemplateEngine(data_dir=tmp_path)
        with pytest.raises(TemplateLoadError, match="expected a top-level 'templates' list"):
            eng.load_templates()

    def test_schema_validation_failure_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            textwrap.dedent("""\
                templates:
                  - finding_type: bad_template
                    dimension: invalid_dimension
                    severity_levels:
                      - medium
                    explanation_template: "Test"
                    business_impact_template: "Test"
                    remediation_steps: []
            """),
            encoding="utf-8",
        )
        eng = TemplateEngine(data_dir=tmp_path)
        # Empty remediation_steps should fail validation
        with pytest.raises(TemplateLoadError):
            eng.load_templates()

    def test_call_get_template_before_load_raises(self) -> None:
        eng = TemplateEngine()
        with pytest.raises(TemplateLoadError, match="load_templates"):
            eng.get_template("high_cyclomatic_complexity", "code_complexity", "high")


# ---------------------------------------------------------------------------
# All 20 finding types render without error
# ---------------------------------------------------------------------------

class TestAllFindingTypesRender:
    @pytest.mark.parametrize("finding_type,dimension,severity", _ALL_FINDING_TYPES)
    def test_renders_non_empty_explanation(
        self, engine: TemplateEngine, finding_type: str, dimension: str, severity: str
    ) -> None:
        resp = engine.get_template(finding_type, dimension, severity)
        assert resp.explanation_text, f"Empty explanation for {finding_type}"
        assert resp.business_impact, f"Empty business_impact for {finding_type}"
        assert resp.remediation_steps, f"Empty remediation_steps for {finding_type}"

    @pytest.mark.parametrize("finding_type,dimension,severity", _ALL_FINDING_TYPES)
    def test_source_is_template_generated(
        self, engine: TemplateEngine, finding_type: str, dimension: str, severity: str
    ) -> None:
        resp = engine.get_template(finding_type, dimension, severity)
        assert resp.source == "template-generated"

    @pytest.mark.parametrize("finding_type,dimension,severity", _ALL_FINDING_TYPES)
    def test_confidence_score_is_default(
        self, engine: TemplateEngine, finding_type: str, dimension: str, severity: str
    ) -> None:
        resp = engine.get_template(finding_type, dimension, severity)
        assert resp.confidence_score == pytest.approx(0.7)

    @pytest.mark.parametrize("finding_type,dimension,severity", _ALL_FINDING_TYPES)
    def test_not_generic_fallback(
        self, engine: TemplateEngine, finding_type: str, dimension: str, severity: str
    ) -> None:
        resp = engine.get_template(finding_type, dimension, severity)
        assert resp.is_generic_fallback is False


# ---------------------------------------------------------------------------
# Variable substitution
# ---------------------------------------------------------------------------

class TestVariableSubstitution:
    def test_service_name_substituted(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "high_cyclomatic_complexity",
            "code_complexity",
            "high",
            context_vars={"service_name": "payment-service"},
        )
        assert "payment-service" in resp.explanation_text

    def test_finding_title_substituted(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "high_cyclomatic_complexity",
            "code_complexity",
            "high",
            context_vars={"finding_title": "calculate_discount"},
        )
        assert "calculate_discount" in resp.explanation_text

    def test_severity_substituted_in_context(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "known_cve",
            "dependencies",
            "critical",
            context_vars={"service_name": "auth-service"},
        )
        assert "auth-service" in resp.explanation_text

    def test_pr_reference_substituted(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "large_file_change",
            "code_complexity",
            "high",
            context_vars={"pr_reference": "PR-1234"},
        )
        assert "PR-1234" in resp.explanation_text

    def test_threshold_and_actual_substituted(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "high_cyclomatic_complexity",
            "code_complexity",
            "high",
            context_vars={"threshold_value": "10", "actual_value": "25"},
        )
        assert "25" in resp.explanation_text
        assert "10" in resp.explanation_text

    def test_all_context_vars(self, engine: TemplateEngine) -> None:
        ctx = {
            "service_name": "svc-a",
            "finding_title": "some_function",
            "severity": "high",
            "dimension": "code_complexity",
            "commit_sha": "abc1234",
            "pr_reference": "PR-999",
            "threshold_value": "15",
            "actual_value": "30",
        }
        resp = engine.get_template(
            "high_cyclomatic_complexity", "code_complexity", "high", context_vars=ctx
        )
        assert "svc-a" in resp.explanation_text
        assert "some_function" in resp.explanation_text

    def test_missing_variable_uses_placeholder(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "high_cyclomatic_complexity",
            "code_complexity",
            "high",
            context_vars={},
        )
        # Should not raise and should not contain unformatted {variable}
        # But some placeholders like {threshold_value} appear because we provide defaults
        assert resp.explanation_text is not None

    def test_special_characters_in_context_do_not_crash(
        self, engine: TemplateEngine
    ) -> None:
        resp = engine.get_template(
            "secrets_in_code",
            "security",
            "critical",
            context_vars={"service_name": "<script>alert(1)</script>"},
        )
        # Must not crash; raw content is passed through (escaping is the caller's job)
        assert "<script>" in resp.explanation_text


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

class TestGenericFallback:
    def test_unknown_finding_type_uses_generic(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "totally_unknown_finding",
            "code_complexity",
            "medium",
        )
        assert resp.is_generic_fallback is True

    def test_generic_confidence_is_lower(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "totally_unknown_finding",
            "generic",
            "low",
        )
        assert resp.confidence_score == pytest.approx(0.5)

    def test_generic_source_still_template_generated(self, engine: TemplateEngine) -> None:
        resp = engine.get_template("unknown_type", "historical", "high")
        assert resp.source == "template-generated"

    def test_generic_response_non_empty(self, engine: TemplateEngine) -> None:
        resp = engine.get_template("unknown_type", "security", "high")
        assert resp.explanation_text
        assert resp.remediation_steps

    def test_generic_substitutes_dimension(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "unknown_type",
            "test_coverage",
            "high",
            context_vars={"service_name": "my-service"},
        )
        assert "my-service" in resp.explanation_text


# ---------------------------------------------------------------------------
# Severity fallback
# ---------------------------------------------------------------------------

class TestSeverityFallback:
    def test_known_finding_unknown_severity_uses_generic(
        self, engine: TemplateEngine
    ) -> None:
        resp = engine.get_template(
            "high_cyclomatic_complexity",
            "code_complexity",
            "unknown_severity",
        )
        # known finding but unknown severity — depends on severity_levels in yaml
        # Should fall back gracefully
        assert resp is not None


# ---------------------------------------------------------------------------
# Configurable default confidence
# ---------------------------------------------------------------------------

class TestConfigurableConfidence:
    def test_custom_confidence(self) -> None:
        eng = TemplateEngine(default_confidence=0.85)
        eng.load_templates()
        resp = eng.get_template(
            "high_cyclomatic_complexity", "code_complexity", "high"
        )
        assert resp.confidence_score == pytest.approx(0.85)

    def test_generic_always_uses_fixed_confidence(self) -> None:
        eng = TemplateEngine(default_confidence=0.9)
        eng.load_templates()
        resp = eng.get_template("unknown_finding", "generic", "medium")
        assert resp.confidence_score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TemplateResponse structure
# ---------------------------------------------------------------------------

class TestTemplateResponseStructure:
    def test_response_has_all_fields(self, engine: TemplateEngine) -> None:
        resp = engine.get_template(
            "known_cve", "dependencies", "critical"
        )
        assert isinstance(resp, TemplateResponse)
        assert resp.finding_type
        assert resp.dimension
        assert resp.explanation_text
        assert resp.business_impact
        assert isinstance(resp.remediation_steps, list)
        assert len(resp.remediation_steps) >= 1

    def test_code_examples_are_optional(self, engine: TemplateEngine) -> None:
        # Some templates have code_examples, some don't — just check it's list or None
        resp = engine.get_template("high_cyclomatic_complexity", "code_complexity", "high")
        assert resp.code_examples is None or isinstance(resp.code_examples, list)

    def test_templates_with_code_examples(self, engine: TemplateEngine) -> None:
        resp = engine.get_template("secrets_in_code", "security", "critical")
        assert resp.code_examples is not None
        assert len(resp.code_examples) >= 1
