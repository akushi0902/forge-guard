"""FindingRepository: async CRUD for the findings table."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository
from forgeguard.services.domain.finding_status import FindingStatus, VALID_TRANSITIONS

logger = structlog.get_logger(__name__)

_VALID_SEVERITIES = ("critical", "high", "medium", "low")

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "assessment_id", "service_id", "policy_rule_id",
    "severity", "dimension", "status", "title", "description",
    "evidence", "ai_explanation", "confidence_score", "escalation_required",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "assessment_id", "severity", "status", "title", "description", "evidence",
    "ai_explanation", "confidence_score", "resolved_at", "escalation_required",
    "version",
})


class FindingRepository(BaseRepository):
    _table = "findings"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        # findings has no deleted_at; include_deleted is accepted but unused
        q = "SELECT * FROM findings WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return self._row(row)

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM findings WHERE TRUE"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY id LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def list_by_service(
        self,
        service_id: str | uuid.UUID,
        *,
        severity: list[str] | None = None,
        status: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return findings for a service with optional severity/status filters.

        Cursor-paginated by (created_at DESC, id DESC).  Pass the last row's
        ``{created_at}:{id}`` as *cursor* to get the next page.
        """
        params: list[Any] = [uuid.UUID(str(service_id))]
        idx = 2
        q = "SELECT * FROM findings WHERE service_id = $1"

        if severity:
            placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(severity)))
            q += f" AND severity IN ({placeholders})"
            params.extend(severity)
            idx += len(severity)

        if status:
            placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(status)))
            q += f" AND status IN ({placeholders})"
            params.extend(status)
            idx += len(status)

        if cursor:
            # cursor = "<iso_created_at>:<uuid>" — e.g. "2026-01-01T00:00:00+00:00:uuid-val"
            try:
                ts_part, id_part = cursor.rsplit(":", 1)
                q += f" AND (created_at, id) < (${idx}::timestamptz, ${idx + 1})"
                params.append(ts_part)
                params.append(uuid.UUID(id_part))
                idx += 2
            except (ValueError, AttributeError):
                logger.warning("findings.list_by_service.invalid_cursor", cursor=cursor)

        q += f" ORDER BY created_at DESC, id DESC LIMIT ${idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("findings", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def bulk_create_findings(
        self, findings_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Insert multiple findings in a single transaction.

        Uses INSERT … ON CONFLICT (service_id, policy_rule_id) WHERE status='open'
        DO NOTHING to silently skip duplicates (the unique partial index enforces
        dedup at the DB level as a safety net behind the application-level check).

        Raises on any other constraint violation.
        """
        if not findings_data:
            return []

        results: list[dict[str, Any]] = []

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for data in findings_data:
                    filtered = [
                        (col, val) for col, val in data.items()
                        if col in _ALLOWED_INSERT
                    ]
                    if not filtered:
                        continue
                    col_names = ", ".join(col for col, _ in filtered)
                    placeholders = ", ".join(f"${i + 1}" for i in range(len(filtered)))
                    values = [val for _, val in filtered]
                    q = (
                        f"INSERT INTO findings ({col_names}) VALUES ({placeholders}) "
                        "ON CONFLICT (service_id, policy_rule_id) WHERE status = 'open' "
                        "DO NOTHING RETURNING *"
                    )
                    row = await conn.fetchrow(q, *values)
                    if row is not None:
                        results.append(dict(row))

        return results

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        set_clause, values = self._safe_update_clause(_ALLOWED_UPDATE, data)
        if not set_clause:
            return await self.get_by_id(id)
        values.append(uuid.UUID(str(id)))
        q = (
            f"UPDATE findings SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "Findings are not soft-deleted; use update_status('remediated') instead"
        )

    async def find_by_service_and_severity(
        self, service_id: str | uuid.UUID, severity: str
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM findings WHERE service_id = $1 AND severity = $2 "
            "ORDER BY created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(service_id)), severity)
        return self._rows(rows)

    async def find_by_assessment(
        self, assessment_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM findings WHERE assessment_id = $1 "
            "ORDER BY severity, created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(assessment_id)))
        return self._rows(rows)

    async def find_existing_open_finding(
        self,
        service_id: str | uuid.UUID,
        policy_rule_id: str | uuid.UUID,
    ) -> dict[str, Any] | None:
        """Return the open finding for (service, rule) or None, locking the row.

        Uses SELECT … FOR UPDATE to prevent race conditions when multiple
        concurrent assessments check for the same finding simultaneously.
        Must be called inside an explicit transaction to hold the lock.
        """
        q = (
            "SELECT * FROM findings "
            "WHERE service_id = $1 AND policy_rule_id = $2 AND status = 'open' "
            "FOR UPDATE"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(service_id)), uuid.UUID(str(policy_rule_id)))
        return self._row(row)

    async def count_by_severity(
        self, service_id: str | uuid.UUID
    ) -> dict[str, int]:
        q = (
            "SELECT severity, COUNT(*) AS count FROM findings "
            "WHERE service_id = $1 AND status NOT IN ('remediated','exception_granted') "
            "GROUP BY severity"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(service_id)))
        counts: dict[str, int] = {sev: 0 for sev in _VALID_SEVERITIES}
        for row in rows:
            counts[row["severity"]] = int(row["count"])
        return counts

    async def update_status(
        self, id: str | uuid.UUID, status: str
    ) -> dict[str, Any] | None:
        """Transition finding status, validating against VALID_TRANSITIONS.

        Raises ValueError for invalid transitions, listing the valid next states.
        Returns None when the finding does not exist.
        """
        finding = await self.get_by_id(id)
        if finding is None:
            return None

        try:
            current = FindingStatus(finding["status"])
            target = FindingStatus(status)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        allowed = VALID_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            valid_values = sorted(s.value for s in allowed)
            raise ValueError(
                f"Invalid status transition from '{current.value}' to '{target.value}'. "
                f"Valid transitions from '{current.value}': {valid_values}"
            )

        resolved_at_clause = ""
        if target == FindingStatus.REMEDIATED:
            resolved_at_clause = ", resolved_at = NOW()"

        q = (
            f"UPDATE findings SET status = $1, updated_at = NOW(){resolved_at_clause} "
            "WHERE id = $2 RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, target.value, uuid.UUID(str(id)))
        return self._row(row)

    async def update_with_optimistic_lock(
        self,
        id: str | uuid.UUID,
        expected_version: int,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update finding fields only when the version matches, then increment version.

        Returns the updated row, or None if the finding does not exist.

        Raises:
            ConflictError: If the row was modified concurrently (version mismatch).
        """
        from forgeguard.core.exceptions import ConflictError  # noqa: PLC0415

        set_clause, values = self._safe_update_clause(_ALLOWED_UPDATE, data)
        if not set_clause:
            # No updatable fields; check version only
            existing = await self.get_by_id(id)
            if existing is None:
                return None
            if existing.get("version", 1) != expected_version:
                raise ConflictError(
                    "Concurrent re-evaluation in progress — the finding was modified.",
                    details={"error_code": "OPTIMISTIC_LOCK_CONFLICT"},
                )
            return existing

        fid = uuid.UUID(str(id))
        # Append the version increment and WHERE version = $N clause
        values.append(fid)
        values.append(expected_version)
        q = (
            f"UPDATE findings SET {set_clause}, version = version + 1, updated_at = NOW() "
            f"WHERE id = ${len(values) - 1} AND version = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)

        if row is None:
            # Check if the finding exists at all (to distinguish 404 from 409)
            existing = await self.get_by_id(id)
            if existing is None:
                return None
            raise ConflictError(
                "Concurrent re-evaluation in progress — the finding was modified.",
                details={"error_code": "OPTIMISTIC_LOCK_CONFLICT"},
            )
        return self._row(row)
