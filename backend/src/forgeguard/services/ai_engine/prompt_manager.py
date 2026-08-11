"""PromptManager: loads and renders versioned prompt templates.

Uses :class:`~forgeguard.data.repositories.prompt_template_repository.PromptTemplateRepository`
to retrieve the active template for a given dimension and severity, then
renders it with caller-supplied variables using Python's standard
:class:`string.Template` ($ substitution, no code execution).

Variable substitution is intentionally sandboxed:
    - Uses ``string.Template.safe_substitute()`` — unknown variables are left
      as-is (``$varname``), never raise KeyError, and never execute code.
    - Variable values are converted to strings before substitution; nested
      structures are flattened with repr() to prevent injection.
    - Template text is never eval'd or exec'd.

Fallback behaviour:
    - If no active template exists for the requested (dimension, severity),
      PromptManager returns the GENERIC_FALLBACK_TEMPLATE and logs a warning.
    - Callers can detect fallback via the ``is_fallback`` flag on the returned
      :class:`RenderResult`.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Any

import structlog

from forgeguard.data.models.prompt_template import PromptTemplate
from forgeguard.data.repositories.prompt_template_repository import (
    PromptTemplateRepository,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Generic catch-all template — used when no specific template is found.
# ---------------------------------------------------------------------------
_GENERIC_FALLBACK_TEXT = (
    "You are a senior software engineer reviewing a release readiness finding.\n\n"
    "Finding: $finding_title\n"
    "Dimension: $dimension\n"
    "Severity: $severity\n\n"
    "Evidence:\n$evidence\n\n"
    "Policy rule: $policy_rule_description\n\n"
    "Please provide:\n"
    "1. A concise explanation of why this finding matters.\n"
    "2. Three specific, actionable remediation steps the engineering team can take.\n"
    "3. An estimate of the effort required (low/medium/high) for each step.\n"
)

_GENERIC_FALLBACK_VARIABLES = {
    "finding_title": "str",
    "dimension": "str",
    "severity": "str",
    "evidence": "str",
    "policy_rule_description": "str",
}


class PromptRenderError(Exception):
    """Raised when template rendering fails irrecoverably."""


@dataclass
class RenderResult:
    """Output of a successful template render."""

    rendered_prompt: str
    template_name: str
    template_version: int
    dimension: str
    severity_level: str
    is_fallback: bool = False
    missing_variables: list[str] = field(default_factory=list)


class PromptManager:
    """Loads and renders versioned prompt templates.

    Args:
        repository: Injected :class:`PromptTemplateRepository` for DB access.
    """

    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_template(
        self, dimension: str, severity: str
    ) -> PromptTemplate | None:
        """Return the active :class:`PromptTemplate` for *dimension* + *severity*.

        Returns ``None`` when no active template exists; callers should fall
        back to the generic template via :meth:`render_generic`.
        """
        return await self._repo.get_active_by_dimension_severity(dimension, severity)

    async def render(
        self,
        dimension: str,
        severity: str,
        variables: dict[str, Any],
    ) -> RenderResult:
        """Load the active template and render it with *variables*.

        Falls back to the generic built-in template when no specific template
        is found.  Never raises on missing variables — they are left as
        ``$varname`` placeholders and recorded in :attr:`RenderResult.missing_variables`.

        Args:
            dimension:  Policy dimension (e.g. ``"security"``).
            severity:   Severity level (e.g. ``"high"``).
            variables:  Dict of substitution values.  Keys should match the
                        ``$variable`` placeholders in the template text.

        Returns:
            A :class:`RenderResult` with the rendered prompt and metadata.

        Raises:
            PromptRenderError: Only if the template text itself is so malformed
                that even safe_substitute cannot proceed.
        """
        template = await self.load_template(dimension, severity)

        if template is None:
            logger.warning(
                "prompt_template_not_found",
                dimension=dimension,
                severity=severity,
                fallback="generic",
            )
            return self._render_generic(dimension, severity, variables)

        return self._render_template(template, variables, is_fallback=False)

    def render_generic(
        self, dimension: str, severity: str, variables: dict[str, Any]
    ) -> RenderResult:
        """Render the built-in generic fallback template synchronously."""
        return self._render_generic(dimension, severity, variables)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_template(
        self,
        template: PromptTemplate,
        variables: dict[str, Any],
        is_fallback: bool,
    ) -> RenderResult:
        safe_vars = self._sanitise_variables(variables)
        rendered, missing = self._safe_substitute(template.template_text, safe_vars)

        if missing:
            logger.warning(
                "prompt_template_missing_variables",
                template_name=template.name,
                template_version=template.version,
                missing=missing,
            )

        return RenderResult(
            rendered_prompt=rendered,
            template_name=template.name,
            template_version=template.version,
            dimension=template.dimension,
            severity_level=template.severity_level,
            is_fallback=is_fallback,
            missing_variables=missing,
        )

    def _render_generic(
        self, dimension: str, severity: str, variables: dict[str, Any]
    ) -> RenderResult:
        safe_vars = self._sanitise_variables(variables)
        rendered, missing = self._safe_substitute(_GENERIC_FALLBACK_TEXT, safe_vars)
        return RenderResult(
            rendered_prompt=rendered,
            template_name="__generic_fallback__",
            template_version=0,
            dimension=dimension,
            severity_level=severity,
            is_fallback=True,
            missing_variables=missing,
        )

    @staticmethod
    def _sanitise_variables(variables: dict[str, Any]) -> dict[str, str]:
        """Flatten all values to str for safe substitution.

        Nested dicts/lists are repr()'d so they appear literally in the prompt
        rather than raising TypeError or enabling injection.
        """
        result: dict[str, str] = {}
        for key, value in variables.items():
            if isinstance(value, str):
                result[key] = value
            elif value is None:
                result[key] = ""
            elif isinstance(value, (dict, list)):
                result[key] = repr(value)
            else:
                result[key] = str(value)
        return result

    @staticmethod
    def _safe_substitute(
        template_text: str, variables: dict[str, str]
    ) -> tuple[str, list[str]]:
        """Run safe_substitute and detect unreplaced placeholders.

        Returns ``(rendered, missing_variable_names)``.
        """
        try:
            tpl = string.Template(template_text)
            rendered = tpl.safe_substitute(variables)
        except Exception as exc:
            raise PromptRenderError(
                f"Template substitution failed: {exc}"
            ) from exc

        # Detect unreplaced $var placeholders in the rendered output.
        # safe_substitute leaves them as $varname or ${varname}.
        missing: list[str] = []
        try:
            pattern = string.Template.pattern
            for match in pattern.finditer(rendered):
                braced = match.group("braced")
                named = match.group("named")
                placeholder = braced or named
                if placeholder and placeholder not in missing:
                    missing.append(placeholder)
        except Exception:
            pass  # missing-variable detection is best-effort

        return rendered, missing
