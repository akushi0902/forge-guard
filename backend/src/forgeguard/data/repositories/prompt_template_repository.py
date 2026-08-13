"""Async repository for PromptTemplate persistence operations.

All methods accept a SQLAlchemy async session and delegate all query
construction to SQLAlchemy core — no raw SQL strings.

Version management contract:
    - ``create``       inserts version=1 (or 1 if no prior version exists).
    - ``update``       inserts a NEW row with version=max(existing)+1 and sets
                       the previous row's is_active=False. Previous versions are
                       never deleted.
    - ``deactivate``   sets is_active=False on all versions of a template name.

Lookup contract:
    - ``get_active_by_dimension_severity`` returns the highest-version active
      row for the given dimension + severity_level, or None if none exists.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forgeguard.data.models.prompt_template import PromptTemplate

logger = structlog.get_logger(__name__)


class PromptTemplateRepository:
    """Data access object for the ``prompt_templates`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_active_by_dimension_severity(
        self, dimension: str, severity_level: str
    ) -> PromptTemplate | None:
        """Return the highest-version active template for dimension + severity.

        Returns ``None`` when no active template exists for the combination.
        """
        stmt = (
            select(PromptTemplate)
            .where(
                PromptTemplate.dimension == dimension,
                PromptTemplate.severity_level == severity_level,
                PromptTemplate.is_active.is_(True),
            )
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, template_id: uuid.UUID) -> PromptTemplate | None:
        """Return a template by primary key regardless of is_active."""
        stmt = select(PromptTemplate).where(PromptTemplate.id == template_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_name_and_version(
        self, name: str, version: int
    ) -> PromptTemplate | None:
        """Return a template by (name, version) unique key."""
        stmt = select(PromptTemplate).where(
            PromptTemplate.name == name,
            PromptTemplate.version == version,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_all(
        self,
        *,
        dimension: str | None = None,
        severity_level: str | None = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PromptTemplate], int]:
        """Return paginated templates with optional filters.

        Returns:
            A ``(items, total)`` tuple where ``total`` is the count before
            pagination so callers can compute cursor/page info.
        """
        filters = []
        if dimension:
            filters.append(PromptTemplate.dimension == dimension)
        if severity_level:
            filters.append(PromptTemplate.severity_level == severity_level)
        if active_only:
            filters.append(PromptTemplate.is_active.is_(True))

        count_stmt = select(func.count(PromptTemplate.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        list_stmt = (
            select(PromptTemplate)
            .order_by(PromptTemplate.name, PromptTemplate.version.desc())
            .limit(limit)
            .offset(offset)
        )
        if filters:
            list_stmt = list_stmt.where(*filters)
        list_result = await self._session.execute(list_stmt)
        items = list(list_result.scalars().all())

        return items, total

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create(
        self,
        name: str,
        template_text: str,
        variables: dict[str, Any],
        dimension: str,
        severity_level: str,
        created_by: uuid.UUID | None = None,
    ) -> PromptTemplate:
        """Insert a new template at version 1.

        The caller is responsible for committing or rolling back the session.
        """
        template = PromptTemplate(
            name=name,
            version=1,
            template_text=template_text,
            variables=variables,
            dimension=dimension,
            severity_level=severity_level,
            is_active=True,
            created_by=created_by,
        )
        self._session.add(template)
        await self._session.flush()  # populate server-generated id/timestamps
        logger.info(
            "prompt_template_created",
            template_id=str(template.id),
            name=name,
            dimension=dimension,
            severity_level=severity_level,
        )
        return template

    async def update(
        self,
        existing: PromptTemplate,
        *,
        template_text: str | None = None,
        variables: dict[str, Any] | None = None,
        updated_by: uuid.UUID | None = None,
    ) -> PromptTemplate:
        """Create a new version row and deactivate the previous version.

        Args:
            existing:      The current active PromptTemplate row.
            template_text: New prompt text; uses existing value if not supplied.
            variables:     New variable schema; uses existing value if not supplied.
            updated_by:    User performing the update.

        Returns:
            The newly inserted PromptTemplate row (version+1, is_active=True).
        """
        # Deactivate the existing version first.
        await self._session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == existing.id)
            .values(is_active=False)
        )

        new_template = PromptTemplate(
            name=existing.name,
            version=existing.version + 1,
            template_text=template_text if template_text is not None else existing.template_text,
            variables=variables if variables is not None else existing.variables,
            dimension=existing.dimension,
            severity_level=existing.severity_level,
            is_active=True,
            created_by=updated_by,
        )
        self._session.add(new_template)
        await self._session.flush()
        logger.info(
            "prompt_template_updated",
            template_id=str(new_template.id),
            name=existing.name,
            old_version=existing.version,
            new_version=new_template.version,
        )
        return new_template

    async def deactivate(self, template_id: uuid.UUID) -> PromptTemplate | None:
        """Set is_active=False on a template row.

        Returns the updated row, or ``None`` if not found.
        """
        template = await self.get_by_id(template_id)
        if template is None:
            return None
        await self._session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(is_active=False)
        )
        await self._session.flush()
        # Re-fetch to get updated state.
        return await self.get_by_id(template_id)
