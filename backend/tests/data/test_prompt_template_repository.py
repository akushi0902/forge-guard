"""Unit tests for PromptTemplateRepository.

Uses a mock AsyncSession to test business logic (version increment,
deactivation) without requiring a database.

Tests that require real DB persistence are tagged @pytest.mark.integration
and skipped in standard runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.data.models.prompt_template import PromptTemplate
from forgeguard.data.repositories.prompt_template_repository import (
    PromptTemplateRepository,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_template(
    name: str = "test_tpl",
    version: int = 1,
    dimension: str = "security",
    severity_level: str = "high",
    is_active: bool = True,
    template_text: str = "Finding: $finding_title",
    variables: dict | None = None,
) -> PromptTemplate:
    """Build a mock PromptTemplate with sane defaults."""
    tpl = MagicMock(spec=PromptTemplate)
    tpl.id = uuid.uuid4()
    tpl.name = name
    tpl.version = version
    tpl.template_text = template_text
    tpl.variables = variables or {"finding_title": "str"}
    tpl.dimension = dimension
    tpl.severity_level = severity_level
    tpl.is_active = is_active
    tpl.created_by = None
    tpl.created_at = datetime.now(tz=timezone.utc)
    tpl.updated_at = datetime.now(tz=timezone.utc)
    return tpl


def _make_session(scalar_result=None) -> MagicMock:
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    # Default scalar result for execute()
    scalar_mock = MagicMock()
    scalar_mock.scalars.return_value.first.return_value = scalar_result
    scalar_mock.scalar_one.return_value = 0
    session.execute.return_value = scalar_mock
    return session


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

class TestCreate:
    async def test_create_adds_template_to_session(self) -> None:
        session = _make_session()
        repo = PromptTemplateRepository(session)

        tpl = await repo.create(
            name="my_template",
            template_text="Hello $name.",
            variables={"name": "str"},
            dimension="security",
            severity_level="high",
        )
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_create_sets_version_1(self) -> None:
        session = _make_session()
        repo = PromptTemplateRepository(session)
        tpl = await repo.create(
            name="v1_tpl",
            template_text="Text.",
            variables={},
            dimension="security",
            severity_level="high",
        )
        assert tpl.version == 1

    async def test_create_is_active_by_default(self) -> None:
        session = _make_session()
        repo = PromptTemplateRepository(session)
        tpl = await repo.create(
            name="active_tpl",
            template_text="Text.",
            variables={},
            dimension="code_quality",
            severity_level="critical",
        )
        assert tpl.is_active is True

    async def test_create_stores_name_and_text(self) -> None:
        session = _make_session()
        repo = PromptTemplateRepository(session)
        tpl = await repo.create(
            name="named_tpl",
            template_text="My specific text.",
            variables={},
            dimension="test_coverage",
            severity_level="medium",
        )
        assert tpl.name == "named_tpl"
        assert tpl.template_text == "My specific text."


# ---------------------------------------------------------------------------
# update (version auto-increment)
# ---------------------------------------------------------------------------

class TestUpdate:
    async def test_increments_version(self) -> None:
        existing = _make_template(version=1)
        session = _make_session()
        # get_by_id will be called internally after flush to return new template
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, template_text="New text.")
        assert new_tpl.version == existing.version + 1

    async def test_new_template_is_active(self) -> None:
        existing = _make_template(version=2)
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, template_text="Updated.")
        assert new_tpl.is_active is True

    async def test_inherits_name_dimension_severity(self) -> None:
        existing = _make_template(
            name="my_tpl", dimension="documentation", severity_level="low", version=1
        )
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, template_text="New.")
        assert new_tpl.name == "my_tpl"
        assert new_tpl.dimension == "documentation"
        assert new_tpl.severity_level == "low"

    async def test_uses_provided_template_text(self) -> None:
        existing = _make_template(template_text="Old text.")
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, template_text="Brand new text.")
        assert new_tpl.template_text == "Brand new text."

    async def test_inherits_template_text_when_not_provided(self) -> None:
        existing = _make_template(template_text="Inherited text.")
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, variables={"new_var": "str"})
        assert new_tpl.template_text == "Inherited text."

    async def test_uses_provided_variables(self) -> None:
        existing = _make_template(variables={"old_var": "str"})
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, variables={"new_var": "int"})
        assert new_tpl.variables == {"new_var": "int"}

    async def test_inherits_variables_when_not_provided(self) -> None:
        existing = _make_template(variables={"finding_title": "str"})
        session = _make_session()
        repo = PromptTemplateRepository(session)

        new_tpl = await repo.update(existing, template_text="New.")
        assert new_tpl.variables == {"finding_title": "str"}

    async def test_deactivates_previous_version(self) -> None:
        existing = _make_template(version=1)
        session = _make_session()
        repo = PromptTemplateRepository(session)

        await repo.update(existing, template_text="New.")
        # session.execute must have been called to issue the UPDATE is_active=False
        assert session.execute.await_count >= 1

    async def test_flush_called_for_new_row(self) -> None:
        existing = _make_template()
        session = _make_session()
        repo = PromptTemplateRepository(session)

        await repo.update(existing, template_text="New.")
        session.flush.assert_awaited()

    async def test_triple_increment(self) -> None:
        t1 = _make_template(version=1)
        session = _make_session()
        repo = PromptTemplateRepository(session)

        t2 = await repo.update(t1, template_text="v2.")
        t3 = await repo.update(t2, template_text="v3.")
        assert t3.version == 3


# ---------------------------------------------------------------------------
# deactivate
# ---------------------------------------------------------------------------

class TestDeactivate:
    async def test_returns_none_for_unknown_id(self) -> None:
        session = _make_session(scalar_result=None)
        repo = PromptTemplateRepository(session)
        result = await repo.deactivate(uuid.uuid4())
        assert result is None

    async def test_calls_execute_to_update(self) -> None:
        existing = _make_template()
        session = _make_session(scalar_result=existing)

        # Two execute calls: one for get_by_id SELECT, one for UPDATE
        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalars.return_value.first.return_value = existing
            result.scalar_one.return_value = 1
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)
        repo = PromptTemplateRepository(session)
        await repo.deactivate(existing.id)
        assert call_count >= 1


# ---------------------------------------------------------------------------
# Seed templates render correctly
# ---------------------------------------------------------------------------

class TestSeedTemplates:
    def test_seed_templates_list_has_10_plus_entries(self) -> None:
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES
        assert len(_SEED_TEMPLATES) >= 10

    def test_all_dimensions_covered(self) -> None:
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES
        dims = {t["dimension"] for t in _SEED_TEMPLATES}
        expected = {
            "code_quality",
            "test_coverage",
            "security",
            "documentation",
            "operations_readiness",
        }
        assert dims == expected

    def test_at_least_two_severity_levels_per_dimension(self) -> None:
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES
        from collections import defaultdict
        dim_sev: dict[str, set] = defaultdict(set)
        for t in _SEED_TEMPLATES:
            dim_sev[t["dimension"]].add(t["severity_level"])
        for dim, severities in dim_sev.items():
            assert len(severities) >= 2, f"{dim} has fewer than 2 severity levels"

    def test_all_templates_have_non_empty_text(self) -> None:
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES
        for t in _SEED_TEMPLATES:
            assert t["template_text"].strip(), f"Template {t['name']} has empty text"

    def test_all_templates_have_unique_names(self) -> None:
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES
        names = [t["name"] for t in _SEED_TEMPLATES]
        assert len(names) == len(set(names)), "Duplicate template names found"

    def test_all_seed_templates_render_with_sample_data(self) -> None:
        import string
        from forgeguard.data.seeds.prompt_templates import _SEED_TEMPLATES

        sample_vars = {
            "finding_title": "Test Finding",
            "service_name": "test-service",
            "severity": "high",
            "evidence": "Sample evidence text.",
            "policy_rule_description": "Sample policy rule.",
            "actual_value": "75%",
            "threshold_value": "80%",
        }
        for t in _SEED_TEMPLATES:
            tpl = string.Template(t["template_text"])
            rendered = tpl.safe_substitute(sample_vars)
            assert rendered  # non-empty
            assert len(rendered) > 10
