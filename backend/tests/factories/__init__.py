"""Factory-boy factories for ForgeGuard domain entities.

All factories produce objects with realistic Faker-generated data.

Factories backed by real SQLAlchemy models (e.g. UserFactory) use
``SQLAlchemyModelFactory``.  Factories for entities whose models have
not been defined yet use plain ``factory.Factory`` with dataclass targets
so they can be upgraded seamlessly when models are created.

Usage::

    from tests.factories import UserFactory, ServiceFactory

    # Build in-memory (no DB required)
    user = UserFactory.build()
    service = ServiceFactory.build()

    # Persist to the test database (requires db_session fixture)
    UserFactory._meta.sqlalchemy_session = db_session
    user = UserFactory()          # CREATE + flush
"""

from tests.factories.assessment_factory import AssessmentFactory, ReleaseDecisionFactory
from tests.factories.audit_log_factory import AuditLogFactory
from tests.factories.finding_factory import FindingFactory
from tests.factories.policy_rule_factory import PolicyRuleFactory
from tests.factories.service_factory import ServiceFactory
from tests.factories.user_factory import UserFactory

__all__ = [
    "UserFactory",
    "ServiceFactory",
    "PolicyRuleFactory",
    "FindingFactory",
    "AssessmentFactory",
    "ReleaseDecisionFactory",
    "AuditLogFactory",
]
