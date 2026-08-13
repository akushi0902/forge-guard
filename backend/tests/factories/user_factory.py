"""Factory for the User SQLAlchemy model.

Uses SQLAlchemyModelFactory so test code can persist users directly::

    UserFactory._meta.sqlalchemy_session = db_session
    user = UserFactory()           # INSERT + flush (no commit)
    user = UserFactory.build()     # in-memory only, no DB call

Passwords are hashed at low bcrypt rounds (4) so test suites run fast.
"""

from __future__ import annotations

import uuid

import bcrypt
import factory
from factory.alchemy import SQLAlchemyModelFactory

from forgeguard.data.models.identity import User, VALID_ROLES


def _fast_password_hash(password: str = "TestPass123!") -> str:
    """Return a bcrypt hash at rounds=4 for speed in tests."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


class UserFactory(SQLAlchemyModelFactory):
    """Factory for the User model.

    Each call produces a unique user with a distinct email address.
    The ``role`` cycles through all valid persona values.

    Set ``_meta.sqlalchemy_session`` before calling the factory to
    persist records::

        UserFactory._meta.sqlalchemy_session = db_session
        user = UserFactory(role="developer")
    """

    class Meta:
        model = User
        # Session must be supplied by the calling test or fixture.
        sqlalchemy_session = None
        # flush → write to DB within the test's transaction (no commit)
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    # Sequence ensures email uniqueness across the entire test session.
    email = factory.Sequence(lambda n: f"user{n:04d}@example.com")
    name_encrypted = None
    password_hash = factory.LazyFunction(_fast_password_hash)
    role = factory.Iterator(VALID_ROLES)
    is_active = True
    failed_login_attempts = 0
    locked_until = None
    deleted_at = None
