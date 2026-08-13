"""Shared utility modules for ForgeGuard.

Utilities are pure-function modules with no dependency on the HTTP layer,
database, or external services.  They may be imported by any layer:
middleware, services, API routes, or CLI scripts.

Modules:
    pii_masking   — Deterministic PII masking (email, name, IP address)
    encryption    — AES-256-GCM field-level encryption with key rotation
"""
