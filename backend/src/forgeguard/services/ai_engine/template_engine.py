"""Template Fallback Engine for AI responses.

Loads YAML-based templates from the ``templates/data/`` directory and renders
them with caller-supplied context variables.  Used by :class:`AIEngineService`
when the LLM circuit breaker is open.

Template lookup order:
    1. Exact match on ``(finding_type, severity)``
    2. Exact match on ``finding_type`` with severity ``"any"``
    3. Generic fallback template (``generic_fallback``)

All templates are loaded and validated **once at startup** — invalid YAML
causes :class:`TemplateLoadError`, which must propagate to abort the process
with a clear error message.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import structlog

from .templates.schema import TemplateDimension, TemplateDefinition, TemplateResponse

logger = structlog.get_logger(__name__)
_log = logging.getLogger(__name__)

_TEMPLATES_DATA_DIR = Path(__file__).parent / "templates" / "data"
_GENERIC_FINDING_TYPE = "generic_fallback"
_GENERIC_CONFIDENCE = 0.5


class TemplateLoadError(Exception):
    """Raised at startup when template YAML files are missing or invalid."""


class TemplateNotFoundError(Exception):
    """Raised internally when no template matches — caught and escalated to generic."""


class TemplateRenderError(Exception):
    """Wraps errors during variable substitution."""


class _DefaultFormatDict(dict):
    """dict subclass that returns ``{key}`` for any missing key.

    Prevents ``str.format_map`` from raising ``KeyError`` when a template
    references a variable that the caller did not supply.
    """

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class TemplateEngine:
    """Loads, validates, and renders YAML-based AI response templates.

    Args:
        data_dir:            Path to the directory containing ``*.yaml`` template files.
                             Defaults to the built-in ``templates/data/`` directory.
        default_confidence:  Confidence score for specific-match responses (0.0–1.0).
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        default_confidence: float = 0.7,
    ) -> None:
        self._data_dir = data_dir or _TEMPLATES_DATA_DIR
        self._default_confidence = default_confidence
        # Populated by load_templates():
        # _index[(finding_type, severity)] → TemplateDefinition
        self._index: dict[tuple[str, str], TemplateDefinition] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def load_templates(self) -> None:
        """Read and validate all YAML template files.

        Must be called once at application startup.  Raises
        :class:`TemplateLoadError` if any file is missing, unreadable, or
        fails Pydantic schema validation.
        """
        try:
            import yaml  # noqa: PLC0415 — lazy import; yaml is an optional dep
        except ModuleNotFoundError as exc:
            raise TemplateLoadError(
                "PyYAML is required for the template engine. "
                "Add 'PyYAML>=6.0' to your dependencies."
            ) from exc

        yaml_files = sorted(self._data_dir.glob("*.yaml"))
        if not yaml_files:
            raise TemplateLoadError(
                f"No template YAML files found in {self._data_dir}. "
                "The templates/data/ directory must contain at least one *.yaml file."
            )

        errors: list[str] = []
        loaded_count = 0

        for yaml_file in yaml_files:
            try:
                raw = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
            except Exception as exc:
                errors.append(f"{yaml_file.name}: failed to read/parse — {exc}")
                continue

            templates_raw = data.get("templates") if isinstance(data, dict) else None
            if not isinstance(templates_raw, list):
                errors.append(
                    f"{yaml_file.name}: expected a top-level 'templates' list, got {type(templates_raw).__name__}"
                )
                continue

            for i, raw_tpl in enumerate(templates_raw):
                try:
                    tpl = TemplateDefinition.model_validate(raw_tpl)
                except Exception as exc:
                    errors.append(f"{yaml_file.name}[{i}]: schema validation failed — {exc}")
                    continue

                for severity in tpl.severity_levels:
                    key = (tpl.finding_type, severity)
                    self._index[key] = tpl
                loaded_count += 1

        if errors:
            raise TemplateLoadError(
                f"Template loading failed with {len(errors)} error(s):\n"
                + "\n".join(f"  • {e}" for e in errors)
            )

        logger.info(
            "template_engine_loaded",
            template_count=loaded_count,
            index_entries=len(self._index),
            data_dir=str(self._data_dir),
        )
        self._loaded = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_template(
        self,
        finding_type: str,
        dimension: str,
        severity: str,
        context_vars: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        """Return a rendered template response for the given finding.

        Args:
            finding_type:  Finding type identifier (e.g. ``"high_cyclomatic_complexity"``).
            dimension:     Risk dimension string (e.g. ``"code_complexity"``).
            severity:      Severity level string (e.g. ``"high"``).
            context_vars:  Optional mapping of substitution variables.

        Returns:
            Rendered :class:`~templates.schema.TemplateResponse`.
        """
        if not self._loaded:
            raise TemplateLoadError(
                "TemplateEngine.load_templates() must be called before get_template()."
            )

        ctx = self._build_context(finding_type, dimension, severity, context_vars)
        is_generic = False

        # 1. Exact severity match
        tpl = self._index.get((finding_type, severity))

        # 2. "any" severity fallback for the same finding type
        if tpl is None:
            tpl = self._index.get((finding_type, "any"))

        # 3. Generic fallback
        if tpl is None:
            tpl = self._index.get((_GENERIC_FINDING_TYPE, "any"))
            if tpl is None:
                tpl = next(
                    (t for (ft, _), t in self._index.items() if ft == _GENERIC_FINDING_TYPE),
                    None,
                )
            is_generic = True
            logger.warning(
                "template_fallback_generic",
                finding_type=finding_type,
                dimension=dimension,
                severity=severity,
            )

        if tpl is None:
            raise TemplateNotFoundError(
                f"No template found for finding_type={finding_type!r}, "
                f"severity={severity!r}, and no generic fallback exists."
            )

        was_generic = is_generic
        logger.info(
            "template_fallback_used",
            finding_type=finding_type,
            dimension=dimension,
            severity=severity,
            template_finding_type=tpl.finding_type,
            is_generic=is_generic,
        )

        return self._render(tpl, ctx, was_generic)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(
        self,
        finding_type: str,
        dimension: str,
        severity: str,
        extra: dict[str, Any] | None,
    ) -> _DefaultFormatDict:
        """Merge caller-supplied variables with sensible defaults."""
        defaults: dict[str, Any] = {
            "service_name": "the service",
            "finding_title": finding_type.replace("_", " "),
            "severity": severity,
            "dimension": dimension.replace("_", " "),
            "commit_sha": "[commit]",
            "pr_reference": "[PR]",
            "threshold_value": "[threshold]",
            "actual_value": "[actual]",
        }
        if extra:
            defaults.update(extra)
        return _DefaultFormatDict(defaults)

    def _render(
        self,
        tpl: TemplateDefinition,
        ctx: _DefaultFormatDict,
        is_generic: bool,
    ) -> TemplateResponse:
        """Substitute context variables into all template fields."""
        try:
            explanation = tpl.explanation_template.format_map(ctx)
            business_impact = tpl.business_impact_template.format_map(ctx)
            steps = [step.format_map(ctx) for step in tpl.remediation_steps]
            examples = (
                [ex.format_map(ctx) for ex in tpl.code_examples]
                if tpl.code_examples
                else None
            )
        except Exception as exc:
            logger.error(
                "template_render_error",
                finding_type=tpl.finding_type,
                error=str(exc),
            )
            raise TemplateRenderError(
                f"Failed to render template '{tpl.finding_type}': {exc}"
            ) from exc

        confidence = _GENERIC_CONFIDENCE if is_generic else self._default_confidence

        return TemplateResponse(
            finding_type=tpl.finding_type,
            dimension=tpl.dimension.value,
            explanation_text=explanation.strip(),
            business_impact=business_impact.strip(),
            remediation_steps=steps,
            code_examples=examples,
            source="template-generated",
            confidence_score=confidence,
            is_generic_fallback=is_generic,
        )
