"""Service layer — domain logic modules.

Each sub-module owns its domain logic and communicates with the data layer
through repository abstractions. The service layer must never be imported
directly from the API layer's route handlers other than through the dependency
providers in ``forgeguard.core.dependencies``.

Modules:
    policy_guardian   — Policy evaluation and Engineering Health Score
    release_guardian  — Change analysis and Release Risk Score
    decision_engine   — Combined decision (APPROVE / CONDITIONAL_APPROVE / BLOCK)
    remediation       — Finding lifecycle and AI remediation recommendations
    ai_engine         — LLM provider abstraction and prompt management
    audit             — Immutable audit log writes and compliance queries
    rbac              — Role-based access control enforcement
    demo_app          — Payment Service demo application simulation
"""
