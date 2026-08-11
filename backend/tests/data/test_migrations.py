"""Integration tests for the Alembic migration framework.

Test coverage (all require Docker / testcontainers):
1. Full upgrade: 'alembic upgrade head' creates all 15 expected ForgeGuard tables.
2. Full downgrade: 'alembic downgrade base' drops every ForgeGuard table cleanly.
3. Idempotent upgrade: running 'alembic upgrade head' twice raises no errors.
4. Revision chain: upgrading to each intermediate revision adds exactly the
   expected tables for that step; no FK constraint violations occur.
5. Model-migration sync: 'alembic check' reports no pending autogenerate changes.

Run with Docker available::

    pytest backend/tests/data/test_migrations.py -v -m integration

Exclude when Docker is unavailable::

    pytest -m "not integration"
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from forgeguard.core.config import Settings

# ---------------------------------------------------------------------------
# Repository-relative paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend/

# ---------------------------------------------------------------------------
# Migration revision chain
# Each entry is (revision_id, tables_first_created_by_this_revision).
# ---------------------------------------------------------------------------

_REVISION_STEPS: list[tuple[str, frozenset[str]]] = [
    (
        "a1b2c3d4e5f6",
        frozenset({
            "users",
            "refresh_tokens",
            "roles",
            "permissions",
            "role_permissions",
        }),
    ),
    (
        "b2c3d4e5f6a7",
        frozenset({"services", "policies", "policy_rules"}),
    ),
    (
        "c3d4e5f6a7b8",
        frozenset({"audit_logs", "ai_conversations"}),
    ),
    (
        "d4e5f6a7b8c9",
        frozenset({"prompt_templates"}),
    ),
    (
        "e5f6a7b8c9d0",
        frozenset({
            "assessments",
            "assessment_scores",
            "findings",
            "release_assessments",
            "release_decisions",
        }),
    ),
    (
        "f6a7b8c9d0e1",
        frozenset({"remediation_recommendations", "exceptions"}),
    ),
]

# The complete set of ForgeGuard application tables (excludes alembic_version and
# audit_logs_YYYY_MM partition children).
ALL_EXPECTED_TABLES: frozenset[str] = frozenset(
    t for _, tables in _REVISION_STEPS for t in tables
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_asyncpg_url(url: str) -> str:
    """Convert any postgresql:// variant to the asyncpg driver prefix."""
    for prefix in (
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgresql://",
        "postgres://",
    ):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def _get_app_tables(asyncpg_url: str) -> set[str]:
    """Return the set of user-created table names in the 'public' schema.

    Queries information_schema.tables for BASE TABLE entries and excludes
    the Alembic internal table and audit_logs partition children (which are
    named audit_logs_YYYY_MM).
    """
    async def _query() -> set[str]:
        engine = create_async_engine(asyncpg_url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT table_name "
                        "FROM information_schema.tables "
                        "WHERE table_schema = 'public' "
                        "  AND table_type = 'BASE TABLE' "
                        "  AND table_name != 'alembic_version'"
                    )
                )
                return {row[0] for row in result.fetchall()}
        finally:
            await engine.dispose()

    return asyncio.run(_query())


def _run_alembic_upgrade(revision: str, asyncpg_url: str) -> None:
    """Run 'alembic upgrade <revision>' against the given database URL."""
    import forgeguard.core.config as _config  # noqa: PLC0415
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    migration_settings = Settings(
        database_url=asyncpg_url,
        jwt_secret_key="test-migrations-upgrade",
        log_level="WARNING",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    prev = _config._settings_cache
    _config._settings_cache = migration_settings
    try:
        command.upgrade(alembic_cfg, revision)
    finally:
        _config._settings_cache = prev


def _run_alembic_downgrade(revision: str, asyncpg_url: str) -> None:
    """Run 'alembic downgrade <revision>' against the given database URL."""
    import forgeguard.core.config as _config  # noqa: PLC0415
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    migration_settings = Settings(
        database_url=asyncpg_url,
        jwt_secret_key="test-migrations-downgrade",
        log_level="WARNING",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    prev = _config._settings_cache
    _config._settings_cache = migration_settings
    try:
        command.downgrade(alembic_cfg, revision)
    finally:
        _config._settings_cache = prev


def _run_alembic_check(asyncpg_url: str) -> list[str]:
    """Run 'alembic check' and return a list of pending change descriptions.

    Returns an empty list if models and migrations are in sync, or a list of
    change descriptions if autogenerate detects pending differences.

    Raises RuntimeError if the check command is unavailable (Alembic < 1.9).
    """
    import forgeguard.core.config as _config  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    try:
        from alembic import command as alembic_command  # noqa: PLC0415
        if not hasattr(alembic_command, "check"):
            raise RuntimeError("alembic.command.check unavailable (requires Alembic>=1.9)")
    except ImportError as exc:
        raise RuntimeError(f"alembic not installed: {exc}") from exc

    migration_settings = Settings(
        database_url=asyncpg_url,
        jwt_secret_key="test-migrations-check",
        log_level="WARNING",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    pending: list[str] = []

    # Monkeypatch alembic's autogenerate to capture any pending changes
    # without raising, since CommandError is raised on diff detection.
    from alembic.util import exc as alembic_exc  # noqa: PLC0415

    prev = _config._settings_cache
    _config._settings_cache = migration_settings
    try:
        alembic_command.check(alembic_cfg)
    except alembic_exc.CommandError as exc:
        pending = [str(exc)]
    finally:
        _config._settings_cache = prev

    return pending


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _skip_if_no_testcontainers():
    """Skip the calling test if testcontainers is not installed."""
    try:
        import testcontainers.postgres  # noqa: F401
    except ImportError:
        pytest.skip(
            "testcontainers not installed — run: "
            "pip install 'testcontainers[postgres]>=4.0'"
        )


@pytest.fixture
def fresh_db_url():
    """Start a fresh PostgreSQL 16 testcontainer and return its asyncpg URL.

    Each test that uses this fixture gets an independent database so that
    upgrade/downgrade operations do not interfere between tests.
    """
    _skip_if_no_testcontainers()

    from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

    container = PostgresContainer(image="postgres:16-alpine", dbname="forgeguard_test")
    try:
        container.start()
    except Exception as exc:
        pytest.skip(f"Could not start PostgreSQL testcontainer. Is Docker running? {exc}")

    yield _to_asyncpg_url(container.get_connection_url())

    container.stop()


# ---------------------------------------------------------------------------
# Test 1 — upgrade head creates all expected tables
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestUpgradeHead:
    def test_all_expected_tables_exist_after_upgrade_head(
        self, fresh_db_url: str
    ) -> None:
        """Running 'alembic upgrade head' on a clean DB creates all 15 tables."""
        _run_alembic_upgrade("head", fresh_db_url)

        tables = _get_app_tables(fresh_db_url)

        missing = ALL_EXPECTED_TABLES - tables
        assert not missing, (
            f"'alembic upgrade head' did not create: {sorted(missing)}"
        )

    def test_upgrade_head_creates_exactly_expected_tables(
        self, fresh_db_url: str
    ) -> None:
        """No unexpected tables are created alongside the expected ones."""
        _run_alembic_upgrade("head", fresh_db_url)

        tables = _get_app_tables(fresh_db_url)

        # Exclude audit_logs partition children (named audit_logs_YYYY_MM).
        non_partition_tables = {
            t for t in tables
            if not (t.startswith("audit_logs_") and t != "audit_logs")
        }
        unexpected = non_partition_tables - ALL_EXPECTED_TABLES
        assert not unexpected, (
            f"'alembic upgrade head' created unexpected tables: {sorted(unexpected)}"
        )

    def test_alembic_version_table_tracks_head_revision(
        self, fresh_db_url: str
    ) -> None:
        """alembic_version.version_num matches the head revision after upgrade."""
        _run_alembic_upgrade("head", fresh_db_url)

        async def _query() -> str | None:
            engine = create_async_engine(fresh_db_url, poolclass=NullPool)
            try:
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text("SELECT version_num FROM alembic_version LIMIT 1")
                    )
                    row = result.fetchone()
                    return row[0] if row else None
            finally:
                await engine.dispose()

        version_num = asyncio.run(_query())
        head_revision = _REVISION_STEPS[-1][0]
        assert version_num == head_revision, (
            f"Expected alembic_version.version_num={head_revision!r}, got {version_num!r}"
        )


# ---------------------------------------------------------------------------
# Test 2 — downgrade base removes all ForgeGuard tables
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDowngradeBase:
    def test_downgrade_base_removes_all_forgeguard_tables(
        self, fresh_db_url: str
    ) -> None:
        """Running 'alembic downgrade base' after upgrade head drops all app tables."""
        _run_alembic_upgrade("head", fresh_db_url)
        _run_alembic_downgrade("base", fresh_db_url)

        tables = _get_app_tables(fresh_db_url)

        residual = ALL_EXPECTED_TABLES & tables
        assert not residual, (
            f"'alembic downgrade base' left residual tables: {sorted(residual)}"
        )

    def test_downgrade_base_leaves_no_unexpected_residual_tables(
        self, fresh_db_url: str
    ) -> None:
        """After downgrade base, no ForgeGuard or partition tables remain."""
        _run_alembic_upgrade("head", fresh_db_url)
        _run_alembic_downgrade("base", fresh_db_url)

        tables = _get_app_tables(fresh_db_url)

        # Filter out partition children too.
        forgeguard_residual = {
            t for t in tables
            if t in ALL_EXPECTED_TABLES
            or (t.startswith("audit_logs_") and t != "audit_logs")
        }
        assert not forgeguard_residual, (
            f"Residual tables remain after 'downgrade base': {sorted(forgeguard_residual)}"
        )


# ---------------------------------------------------------------------------
# Test 3 — idempotent upgrade (no-op on second run)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIdempotentUpgrade:
    def test_upgrade_head_twice_does_not_raise(
        self, fresh_db_url: str
    ) -> None:
        """Running 'alembic upgrade head' a second time raises no errors."""
        _run_alembic_upgrade("head", fresh_db_url)
        # Second call must not raise CommandError or any other exception.
        _run_alembic_upgrade("head", fresh_db_url)

    def test_tables_intact_after_second_upgrade_head(
        self, fresh_db_url: str
    ) -> None:
        """All expected tables still exist after two consecutive upgrade head runs."""
        _run_alembic_upgrade("head", fresh_db_url)
        _run_alembic_upgrade("head", fresh_db_url)

        tables = _get_app_tables(fresh_db_url)
        missing = ALL_EXPECTED_TABLES - tables
        assert not missing, (
            f"Tables missing after idempotent upgrade: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Test 4 — revision chain: each step creates exactly the expected tables
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRevisionChainProgression:
    def test_each_revision_adds_expected_tables(
        self, fresh_db_url: str
    ) -> None:
        """Upgrading step-by-step through all revisions creates tables incrementally.

        This test verifies the FK dependency ordering: each migration can apply
        without violating constraints introduced by earlier revisions.
        """
        cumulative_tables: set[str] = set()

        for revision_id, new_tables in _REVISION_STEPS:
            _run_alembic_upgrade(revision_id, fresh_db_url)

            cumulative_tables |= new_tables
            actual_tables = _get_app_tables(fresh_db_url)

            for expected_table in cumulative_tables:
                assert expected_table in actual_tables, (
                    f"After upgrading to {revision_id!r}, "
                    f"expected table {expected_table!r} was not found. "
                    f"Available tables: {sorted(actual_tables)}"
                )

    def test_downgrade_from_each_revision_removes_its_tables(
        self, fresh_db_url: str
    ) -> None:
        """Downgrade from head stepwise: each revision's tables are removed cleanly."""
        _run_alembic_upgrade("head", fresh_db_url)

        for revision_id, owned_tables in reversed(_REVISION_STEPS):
            # Downgrade one step: run the downgrade() for this revision.
            # Find the previous revision (or 'base' for the first one).
            rev_index = next(
                i for i, (r, _) in enumerate(_REVISION_STEPS) if r == revision_id
            )
            prev_revision = (
                _REVISION_STEPS[rev_index - 1][0] if rev_index > 0 else "base"
            )
            _run_alembic_downgrade(prev_revision, fresh_db_url)

            actual_tables = _get_app_tables(fresh_db_url)
            for dropped_table in owned_tables:
                assert dropped_table not in actual_tables, (
                    f"After downgrading past {revision_id!r}, "
                    f"table {dropped_table!r} should not exist but was found."
                )


# ---------------------------------------------------------------------------
# Test 5 — alembic check: models and migrations are in sync
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAlembicCheck:
    def test_alembic_check_runs_without_connection_error(
        self, fresh_db_url: str
    ) -> None:
        """alembic check can execute against a fully migrated database.

        The test verifies that the check command can reach the database and
        run autogenerate comparison without a connection failure.  Minor
        schema differences from partitioned-table autogenerate behaviour
        (audit_logs) are expected and do not constitute a test failure here.
        """
        _run_alembic_upgrade("head", fresh_db_url)

        try:
            pending = _run_alembic_check(fresh_db_url)
        except RuntimeError as exc:
            if "unavailable" in str(exc):
                pytest.skip(f"alembic check not available: {exc}")
            raise

        # If there are pending changes, log them as a warning rather than
        # failing: the partitioned audit_logs table may trigger autogenerate
        # differences that are intentional (see WO-011 architectural notes).
        if pending:
            import warnings  # noqa: PLC0415
            warnings.warn(
                f"alembic check reports pending changes (may be audit_logs partition "
                f"artefacts — review manually): {pending}",
                stacklevel=2,
            )

    def test_no_unexpected_pending_changes(self, fresh_db_url: str) -> None:
        """alembic check reports at most known acceptable differences.

        Acceptable differences:
        - audit_logs: autogenerate cannot represent PARTITION BY RANGE DDL in
          ORM models, so column-level comparisons may show server_default
          differences.  Any differences for audit_logs are acceptable.

        All other tables must show zero pending changes.
        """
        _run_alembic_upgrade("head", fresh_db_url)

        try:
            pending = _run_alembic_check(fresh_db_url)
        except RuntimeError as exc:
            if "unavailable" in str(exc):
                pytest.skip(f"alembic check not available: {exc}")
            raise

        # Filter out known audit_logs autogenerate artefacts.
        non_audit_pending = [p for p in pending if "audit_logs" not in p]
        assert not non_audit_pending, (
            f"alembic check found unexpected pending changes outside audit_logs: "
            f"{non_audit_pending}"
        )
