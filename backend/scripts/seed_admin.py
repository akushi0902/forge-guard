#!/usr/bin/env python
"""Bootstrap the initial Platform Admin user.

Reads ADMIN_EMAIL and ADMIN_PASSWORD from environment variables and creates a
``platform_admin`` user in the database.  If a user with that email already
exists the script exits cleanly — it is idempotent and safe to run in CI.

Usage::

    ADMIN_EMAIL=admin@example.com \
    ADMIN_PASSWORD='S3cret!Password99' \
    DATABASE_URL=postgresql+asyncpg://... \
    python scripts/seed_admin.py

Environment variables
---------------------
ADMIN_EMAIL
    Email address for the Platform Admin account (required).
ADMIN_PASSWORD
    Raw password — must satisfy the ForgeGuard password policy (required).
DATABASE_URL
    asyncpg-compatible PostgreSQL DSN (required if DATABASE_URL is not set
    by other means such as the application's Settings).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

# ---------------------------------------------------------------------------
# Resolve the project source tree so the script can run from anywhere.
# ---------------------------------------------------------------------------
import pathlib

_repo_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))


async def _run() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
    database_url = os.environ.get("DATABASE_URL", "")

    # ---- validate inputs ----
    if not admin_email:
        print("ERROR: ADMIN_EMAIL environment variable is required.", file=sys.stderr)
        sys.exit(1)
    if not admin_password:
        print("ERROR: ADMIN_PASSWORD environment variable is required.", file=sys.stderr)
        sys.exit(1)
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)

    from forgeguard.core.security import hash_password, validate_password_strength  # noqa: PLC0415

    violations = validate_password_strength(admin_password)
    if violations:
        print("ERROR: ADMIN_PASSWORD does not meet security requirements:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        sys.exit(1)

    # Strip the SQLAlchemy driver prefix so asyncpg can use the DSN directly.
    asyncpg_dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")

    import asyncpg  # noqa: PLC0415
    from forgeguard.data.repositories.users import UserRepository  # noqa: PLC0415

    pool = await asyncpg.create_pool(asyncpg_dsn, min_size=1, max_size=2)
    try:
        repo = UserRepository(pool)

        existing = await repo.find_by_email(admin_email)
        if existing is not None:
            print(f"Platform Admin '{admin_email}' already exists — skipping.")
            return

        password_hash = hash_password(admin_password)
        await repo.create({
            "id": uuid.uuid4(),
            "email": admin_email,
            "name_encrypted": b"Platform Admin",
            "password_hash": password_hash,
            "role": "platform_admin",
            "is_active": True,
            "failed_login_attempts": 0,
            "locked_until": None,
        })
        print(f"Platform Admin '{admin_email}' created successfully.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_run())
