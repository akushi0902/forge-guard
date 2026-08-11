"""Unit tests for PromptManager.

Covers:
  - render() with complete variables
  - render() with missing variables (leaves $placeholders, records them)
  - render() with empty template — passes (whitespace validation is in schema)
  - render() with unrecognised placeholders — left as-is
  - render_generic() fallback used when no DB template found
  - _sanitise_variables() flattens nested structures safely
  - version auto-increment logic is tested in test_prompt_template_repository.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.data.models.prompt_template import PromptTemplate
from forgeguard.services.ai_engine.prompt_manager import (
    PromptManager,
    PromptRenderError,
    RenderResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(
    name: str = "test_template",
    version: int = 1,
    template_text: str = "Finding: $finding_title in $service_name. Severity: $severity.",
    dimension: str = "security",
    severity_level: str = "high",
) -> PromptTemplate:
    import uuid
    from datetime import datetime, timezone

    tpl = MagicMock(spec=PromptTemplate)
    tpl.id = uuid.uuid4()
    tpl.name = name
    tpl.version = version
    tpl.template_text = template_text
    tpl.variables = {"finding_title": "str", "service_name": "str", "severity": "str"}
    tpl.dimension = dimension
    tpl.severity_level = severity_level
    tpl.is_active = True
    tpl.created_at = datetime.now(tz=timezone.utc)
    tpl.updated_at = datetime.now(tz=timezone.utc)
    return tpl


def _make_manager(
    template: PromptTemplate | None = None,
) -> PromptManager:
    repo = MagicMock()
    repo.get_active_by_dimension_severity = AsyncMock(return_value=template)
    return PromptManager(repository=repo)


# ---------------------------------------------------------------------------
# render() — template found
# ---------------------------------------------------------------------------

class TestRenderWithTemplate:
    async def test_complete_variables_rendered(self) -> None:
        tpl = _make_template()
        manager = _make_manager(template=tpl)
        result = await manager.render(
            "security",
            "high",
            {
                "finding_title": "SQL injection risk",
                "service_name": "payment-service",
                "severity": "high",
            },
        )
        assert isinstance(result, RenderResult)
        assert "SQL injection risk" in result.rendered_prompt
        assert "payment-service" in result.rendered_prompt
        assert result.is_fallback is False
        assert result.template_name == "test_template"
        assert result.template_version == 1

    async def test_missing_variable_leaves_placeholder(self) -> None:
        tpl = _make_template(
            template_text="Service: $service_name. Finding: $finding_title."
        )
        manager = _make_manager(template=tpl)
        result = await manager.render(
            "security",
            "high",
            {"service_name": "auth-service"},  # missing finding_title
        )
        assert "$finding_title" in result.rendered_prompt
        assert "finding_title" in result.missing_variables

    async def test_unknown_placeholder_left_as_is(self) -> None:
        tpl = _make_template(
            template_text="Text with $unknown_var placeholder."
        )
        manager = _make_manager(template=tpl)
        result = await manager.render("security", "high", {})
        assert "$unknown_var" in result.rendered_prompt
        assert "unknown_var" in result.missing_variables

    async def test_no_missing_variables(self) -> None:
        tpl = _make_template(
            template_text="Finding: $finding_title in $service_name."
        )
        manager = _make_manager(template=tpl)
        result = await manager.render(
            "security", "high",
            {"finding_title": "CVE-2024-1234", "service_name": "api"},
        )
        assert result.missing_variables == []

    async def test_extra_variables_ignored(self) -> None:
        tpl = _make_template(template_text="Hello $finding_title.")
        manager = _make_manager(template=tpl)
        result = await manager.render(
            "security", "high",
            {"finding_title": "CVE-2024", "extra_var": "ignored"},
        )
        assert "CVE-2024" in result.rendered_prompt

    async def test_dimension_severity_passed_to_result(self) -> None:
        tpl = _make_template(dimension="code_quality", severity_level="critical")
        manager = _make_manager(template=tpl)
        result = await manager.render("code_quality", "critical", {})
        assert result.dimension == "code_quality"
        assert result.severity_level == "critical"

    async def test_none_variable_becomes_empty_string(self) -> None:
        tpl = _make_template(template_text="Evidence: $evidence.")
        manager = _make_manager(template=tpl)
        result = await manager.render("security", "high", {"evidence": None})
        assert "Evidence: ." in result.rendered_prompt

    async def test_int_variable_converted_to_str(self) -> None:
        tpl = _make_template(template_text="Score: $score.")
        manager = _make_manager(template=tpl)
        result = await manager.render("security", "high", {"score": 42})
        assert "Score: 42." in result.rendered_prompt

    async def test_dict_variable_repr_safe(self) -> None:
        tpl = _make_template(template_text="Config: $config.")
        manager = _make_manager(template=tpl)
        result = await manager.render("security", "high", {"config": {"key": "val"}})
        # repr() of dict should appear, not raw dict
        assert "$config" not in result.rendered_prompt
        assert "config" not in result.missing_variables


# ---------------------------------------------------------------------------
# render() — generic fallback (no template in DB)
# ---------------------------------------------------------------------------

class TestRenderGenericFallback:
    async def test_falls_back_when_no_template(self) -> None:
        manager = _make_manager(template=None)
        result = await manager.render(
            "code_quality",
            "medium",
            {"finding_title": "High complexity", "dimension": "code_quality"},
        )
        assert result.is_fallback is True
        assert result.template_name == "__generic_fallback__"
        assert result.template_version == 0

    async def test_generic_fallback_contains_finding_title(self) -> None:
        manager = _make_manager(template=None)
        result = await manager.render(
            "test_coverage",
            "low",
            {
                "finding_title": "Missing unit tests",
                "dimension": "test_coverage",
                "severity": "low",
                "evidence": "0% coverage on new module",
                "policy_rule_description": "Coverage must be >= 80%",
            },
        )
        assert "Missing unit tests" in result.rendered_prompt

    async def test_generic_fallback_no_missing_variables_when_all_supplied(
        self,
    ) -> None:
        manager = _make_manager(template=None)
        result = await manager.render(
            "security",
            "high",
            {
                "finding_title": "XSS risk",
                "dimension": "security",
                "severity": "high",
                "evidence": "User input rendered unsanitised",
                "policy_rule_description": "All user input must be escaped",
            },
        )
        assert result.missing_variables == []


# ---------------------------------------------------------------------------
# render_generic() — synchronous variant
# ---------------------------------------------------------------------------

class TestRenderGenericSync:
    def test_render_generic_is_sync(self) -> None:
        manager = _make_manager()
        result = manager.render_generic(
            "documentation",
            "low",
            {
                "finding_title": "Missing README",
                "dimension": "documentation",
                "severity": "low",
                "evidence": "No README.md",
                "policy_rule_description": "All services must have a README",
            },
        )
        assert result.is_fallback is True
        assert result.rendered_prompt


# ---------------------------------------------------------------------------
# _sanitise_variables
# ---------------------------------------------------------------------------

class TestSanitiseVariables:
    def test_string_passthrough(self) -> None:
        result = PromptManager._sanitise_variables({"key": "value"})
        assert result["key"] == "value"

    def test_none_to_empty_string(self) -> None:
        result = PromptManager._sanitise_variables({"key": None})
        assert result["key"] == ""

    def test_int_to_str(self) -> None:
        result = PromptManager._sanitise_variables({"key": 42})
        assert result["key"] == "42"

    def test_dict_to_repr(self) -> None:
        val = {"nested": "dict"}
        result = PromptManager._sanitise_variables({"key": val})
        assert result["key"] == repr(val)

    def test_list_to_repr(self) -> None:
        val = ["a", "b"]
        result = PromptManager._sanitise_variables({"key": val})
        assert result["key"] == repr(val)


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------

class TestLoadTemplate:
    async def test_delegates_to_repository(self) -> None:
        tpl = _make_template()
        repo = MagicMock()
        repo.get_active_by_dimension_severity = AsyncMock(return_value=tpl)
        manager = PromptManager(repository=repo)
        result = await manager.load_template("security", "high")
        assert result is tpl
        repo.get_active_by_dimension_severity.assert_awaited_once_with("security", "high")

    async def test_returns_none_when_not_found(self) -> None:
        repo = MagicMock()
        repo.get_active_by_dimension_severity = AsyncMock(return_value=None)
        manager = PromptManager(repository=repo)
        result = await manager.load_template("security", "low")
        assert result is None
