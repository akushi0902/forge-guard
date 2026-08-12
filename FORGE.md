# Forge Implementation Log

| Field | Value |
|-------|-------|
| Project | dea7ef85-2e4e-417c-9b7a-4fcc49781479 |
| Branch | forge/forgeguard-ai-engineering-rele-8de9d550-run2-102wo |
| Started | 2026-08-11T15:37:07Z |

---

## WO-001: User Story: WO-001 - Scaffold Backend Python FastAPI Modular Monolith Structure
- **Status:** completed
- **Commit:** `baacf06`
- **Files:** 25 (+1166/-1)
- **Duration:** 453ss
- **Approach:** Created the full Python FastAPI modular monolith scaffold using src-layout (backend/src/forgeguard/). Implemented the application factory pattern (create_app()) in main.py, Pydantic BaseSettings in core/config.py reading five environment variables with sensible dev defaults, and FastAPI dependency providers in core/dependencies.py. All eight module packages (api, api/routes, services, data, data/models, data/repositories, middleware, core) were created with __init__.py files. Tooling: ruff.toml (Python 3.12, line-length 120, E/F/W/I/N/UP/B/SIM/RUF rule sets), .importlinter (three contracts enforcing API->Service->Data dependency direction), alembic.ini + alembic/env.py (async engine, naming conventions), and a multi-stage Dockerfile. Test infrastructure includes conftest.py with session-scoped settings/app fixtures and an async httpx client fixture, plus test_app_factory.py with unit and integration tests for the factory.

## WO-002: User Story: WO-002 - Scaffold Frontend React TypeScript Vite Project
- **Status:** completed
- **Commit:** `c8aaa4e`
- **Files:** 21 (+1159/-0)
- **Duration:** 388ss
- **Approach:** Created the full React + TypeScript + Vite frontend scaffold in ui/. Initialized package.json with all pinned runtime (react@19, @mantine/core@7, @tanstack/react-query@5, zustand@4.5, react-router-dom@6, recharts@2.12, axios) and dev dependencies. Configured TypeScript strict mode (noImplicitAny, strictNullChecks, noUnusedLocals, exactOptionalPropertyTypes). Vite configured with React plugin, @ path alias, /api proxy to localhost:8000, and chunked bundle output. Custom Mantine 7 enterprise theme with brand-blue, neutral-gray, and semantic color scales. App.tsx composes MantineProvider → Notifications → QueryClientProvider → RouterProvider. React Router 6 with placeholder routes for all six persona views. Axios client with Bearer token injection and 401/403/429/5xx error handlers using Mantine notifications. Zustand auth store with sessionStorage persistence. Comprehensive TypeScript domain types. Custom test-utils.tsx wrapping components in all providers. Tests covering App mount, dashboard placeholder, and theme integration. Multi-stage Dockerfile (Node 20 build + Nginx Alpine runtime) with security headers.

## WO-003: User Story: WO-003 - Configure Docker Compose Multi-Service Development Stack
- **Status:** completed
- **Commit:** `0d95419`
- **Files:** 11 (+610/-16)
- **Duration:** 523ss
- **Approach:** Created the full Docker Compose multi-service development stack. docker-compose.yml defines four services with strict depends_on health check conditions enforcing db→migration→backend→frontend startup order: forgeguard-db (postgres:16-alpine, pg_isready health check, 1GB/1CPU), forgeguard-migration (backend image with alembic upgrade head, exits 0, service_completed_successfully condition), forgeguard-backend (health check via GET /api/v1/health, 512MB/0.5CPU), forgeguard-frontend (Nginx + React SPA, ports 80/443, 256MB/0.25CPU). nginx/nginx.conf handles TLS termination, HTTP→HTTPS redirect, /api/ reverse proxy to backend with path preservation, SPA fallback routing, and all 6 required security headers. docker-compose.dev.yml adds hot-reload, debug logging, exposed DB and backend ports, and relaxed resource limits. scripts/generate-dev-certs.sh generates self-signed TLS certs with SAN. .env.example documents all variables. Makefile provides setup/up/dev/down/logs/clean targets. Backend was modified to add GET /api/v1/health (canonical Docker health check + Nginx proxy target), and backend/Dockerfile was updated to copy alembic/ and alembic.ini into the runtime stage for the migration container.

## WO-004: User Story: WO-004 - Implement Structured Logging with PII Masking Pipeline
- **Status:** completed
- **Commit:** `11bb06b`
- **Files:** 8 (+926/-23)
- **Duration:** 475ss
- **Approach:** Implemented the full structured logging + PII masking pipeline as a structlog processor chain. core/logging.py owns the processor pipeline (merge_contextvars → add_log_level → TimeStamper → StackInfoRenderer → pii_masking_processor → JSONRenderer/ConsoleRenderer) and bridges stdlib logging through ProcessorFormatter so third-party logs also pass through PII masking. The pii_masking_processor is a deterministic structlog processor that: masks emails to first-char + *** + @domain using regex substitution on any string value, masks IPv4 addresses to first octet only, masks known name fields (name, full_name, etc.) word-by-word, recurses into nested dicts and lists, handles bytes/None/scalars without raising, and wraps errors with [MASKING_ERROR] prefix. RequestIDMiddleware (middleware stage #1) generates UUID v4 per request, clears stale contextvars, binds request_id to structlog context, stores client-supplied ID separately as upstream_request_id (anti-spoofing), and sets X-Request-ID response header. RequestLoggingMiddleware (stage #2) binds actor/resource/operation to structlog context and logs request_started/request_completed with duration_ms. Middleware registration order in main.py is reversed (inner first) so RequestIDMiddleware is outermost and runs first. Tests include 20 parametrized PII masking cases + 14 unit tests for edge cases, and 9 integration tests for the Request ID middleware.

## WO-005: User Story: WO-005 - Implement Health Liveness Readiness and Metrics Endpoints
- **Status:** completed
- **Commit:** `3f6b7b8`
- **Files:** 9 (+596/-33)
- **Duration:** 565ss
- **Approach:** Created api/routes/system.py with three FastAPI route functions under an APIRouter with no auth dependencies: health_check (GET /health) returns status/timestamp/version with zero external calls; readiness_check (GET /ready) creates a transient SQLAlchemy async engine, runs SELECT 1 via asyncio.wait_for with 5s timeout, queries alembic_version, and returns 200/503 with per-check details; metrics_endpoint (GET /metrics) calls prometheus_client.generate_latest() with CONTENT_TYPE_LATEST. Created middleware/metrics.py with MetricsMiddleware (BaseHTTPMiddleware) that records http_requests_total Counter (method/path/status_code), http_request_duration_seconds Histogram (method/path), and exposes db_pool_connections_active Gauge — all at module level to avoid duplicate registration. Updated RequestLoggingMiddleware to accept an exclude_paths frozenset (defaulting to /health, /ready, /metrics) and short-circuit before logging those paths. Updated main.py to remove inline health stubs, register MetricsMiddleware (innermost), keep RequestLoggingMiddleware and RequestIDMiddleware, include the system router at both root and /api/v1 prefix for Nginx proxy backward compat. Updated docker-compose.yml backend health check to /health.

## WO-007: User Story: WO-007 - Identity and Access Domain Schema Tables
- **Status:** completed
- **Commit:** `1f33d7e`
- **Files:** 8 (+979/-9)
- **Duration:** 667ss
- **Approach:** Defined SQLAlchemy 2.0 ORM models (Mapped/mapped_column style) for User, RefreshToken, Role, Permission, and RolePermission in data/models/identity.py. The shared Base declarative class in data/models/__init__.py carries a MetaData with the same naming convention as alembic/env.py so constraint names are deterministic. User has a CHECK constraint on the role column (six ForgeGuard personas), a UNIQUE constraint on email, bytea name_encrypted for AES-256-GCM ciphertext, VARCHAR(60) password_hash for bcrypt output, is_active/failed_login_attempts/locked_until for account lockout, soft-delete via deleted_at, and timezone-aware timestamps. RefreshToken stores only the SHA-256 hash of the token (not the raw token), with FK ON DELETE CASCADE to users and a composite index on (user_id, revoked_at). Role and Permission have UUID PKs and unique name constraints. RolePermission has a composite PK (role_id, permission_id) with FK CASCADE on both sides. The Alembic migration seeds all 6 roles, 10 permissions, and the complete RBAC matrix at upgrade time. alembic/env.py was updated to import Base.metadata enabling autogenerate for future migrations. The .gitignore incorrectly excluded all alembic/versions/*.py files — this was corrected.

## WO-016: User Story: WO-016 - Implement Token Bucket Rate Limiting Middleware
- **Status:** completed
- **Commit:** `fd33744`
- **Files:** 5 (+683/-5)
- **Duration:** 434ss
- **Approach:** Implemented a token bucket rate-limiting middleware using BaseHTTPMiddleware for consistency with the existing middleware stack. The TokenBucket dataclass holds tokens, max_tokens, refill_rate (tokens/second), and last_refill/last_accessed timestamps. refill() calculates elapsed time and adds proportional tokens capped at max_tokens. consume() calls refill() then either decrements one token (allowed) or returns retry_after = ceil((1-tokens)/refill_rate). RateLimiterMiddleware maintains an asyncio.Lock-protected dict keyed by (client_ip, tier). Client IP is extracted from X-Forwarded-For (leftmost entry, RFC 7239) with fallback to ASGI scope client.host and finally 'unknown'. Tier classification matches path against rate_limit_auth_paths prefixes. On ~1% of requests (random.randint check) the _evict_expired() method removes buckets idle for >2x window_seconds. OPTIONS requests skip the check. If bucket logic raises any exception the middleware fails-open (logs warning, allows request). The 429 response body follows the specified contract: {error, message, reference_id, retry_after} with Retry-After header. rate_limit_general, rate_limit_auth, rate_limit_window_seconds, rate_limit_auth_paths were added to Settings with environment-variable overrides. The middleware is registered at position 3 (after RequestIDMiddleware and RequestLoggingMiddleware, before MetricsMiddleware) in create_app().

## WO-017: User Story: WO-017 - Configure CORS and Security Headers Middleware
- **Status:** completed
- **Commit:** `bc1f1b3`
- **Files:** 5 (+735/-6)
- **Duration:** 512ss
- **Approach:** Added CORS configuration fields (CORS_ALLOWED_ORIGINS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS) to Settings with a field_validator that raises ValueError on wildcard origins and a cors_origins_list property. Created SecurityHeadersMiddleware as a raw ASGI send-wrapper that intercepts http.response.start events and appends 7 pre-encoded security header tuples, skipping any already present. Registered both CORSMiddleware (pos 4) and SecurityHeadersMiddleware (pos 5) in main.py's reversed-registration middleware pipeline.

## WO-018: User Story: WO-018 - Implement Pydantic Input Validation Error Formatting
- **Status:** completed
- **Commit:** `b7d4a7e`
- **Files:** 6 (+870/-0)
- **Duration:** 384ss
- **Approach:** Created ForgeGuardBaseModel with strict=True, extra='forbid', str_strip_whitespace=True as the common base for all domain schemas. Defined four reusable Annotated field types (UUIDField, CommitSHAField, EmailField, ScoreField) with regex patterns and range constraints. Created error_handlers.py with format_validation_errors() that flattens Pydantic v2 loc tuples to dot-notation paths (handling list indices as [N]) and produces the ForgeGuard error contract. Two exception handlers cover RequestValidationError→422 and JSONDecodeError→400, both injecting reference_id from request.state.request_id with a safe fallback if the attribute is absent. Registered via register_error_handlers() called in create_app().

## WO-043: User Story: WO-043 - LLM Provider Abstraction with Circuit Breaker
- **Status:** completed
- **Commit:** `fac05ba`
- **Files:** 18 (+2267/-4)
- **Duration:** 829ss
- **Approach:** Built the AI Engine as a layered composition under forgeguard/services/ai_engine/. Bottom layer: models.py (pure dataclasses/enums), errors.py (typed exceptions with no key leakage). Middle layer: abstract LLMProvider ABC, standalone CircuitBreaker (asyncio.Lock + deque-based rolling window, all transitions logged), standalone ResponseCache (OrderedDict LRU + TTL, SHA-256 keys). Provider layer: OpenAIProvider via httpx.AsyncClient with single 429 retry honouring Retry-After. Service layer: AIEngineService composes all three — cache checked before circuit breaker so cached responses survive an open circuit, health_check aggregates all metrics. Wired into DI via get_ai_engine() singleton in core/dependencies.py. All config via Settings (10 new fields).

## WO-068: User Story: WO-068 - Implement Mantine Design System and Shared Components
- **Status:** completed
- **Commit:** `19f6325`
- **Files:** 30 (+2895/-150)
- **Duration:** 786ss
- **Approach:** Built the ForgeGuard Mantine 7 design system from the ground up. Extracted a canonical theme file (forgeguard-theme.ts) with 6 custom color palettes, semantic typography scale, 8px spacing, radius tokens, and shadows. Created 14 shared UI components covering the full design spec: buttons, badges, forms, data visualization (ScoreRing SVG gauge), decision banners, sortable/paginated/expandable DataTable, stat cards, layout primitives (Breadcrumb, Dropdown, Modal, Accordion, Avatar, ServiceCard). Added 3 layout components (Sidebar with RBAC filtering and Zustand-persisted collapse state, TopBar with service selector and dark mode toggle, MainContent). Wrote Vitest + Testing Library tests for every component covering default render, variants, accessibility attributes, click handlers, and empty/edge states.

## WO-094: User Story: WO-094 - Bootstrap Backend pytest Framework and Test Infrastructure
- **Status:** completed
- **Commit:** `5d2e2d3`
- **Files:** 15 (+1204/-33)
- **Duration:** 1027ss
- **Approach:** Extended the existing pytest infrastructure (which already had asyncio_mode=auto, test_settings, app, async_client) with: (1) testcontainers-based PostgreSQL fixture chain (postgres_container → db_url → apply_migrations → db_engine → db_session) using synchronous session-scope fixtures to avoid event-loop complications, and NullPool for clean per-test connection lifecycle; (2) test_client and authenticated_client (JWT factory via PyJWT) fixtures; (3) factory-boy factories for all 7 domain entities — UserFactory uses SQLAlchemyModelFactory with the real User model; the remaining 6 factories use plain factory.Factory with Python dataclasses since their SQLAlchemy models don't exist yet (upgrading to SQLAlchemyModelFactory requires only a Meta.model swap); (4) unit smoke tests (no Docker) covering all fixtures and factory.build() calls; (5) integration smoke tests covering db_session INSERT/SELECT/rollback isolation and factory persistence; (6) make test / make test-ci targets. Coverage fail_under kept at 0 in config (separate CI gate pattern) per the constraint that it must not block the test suite.

## WO-006: User Story: WO-006 - Configure Forge Shipping CI/CD Pipeline with Gates
- **Status:** completed
- **Commit:** `dbe60a0`
- **Files:** 7 (+946/-0)
- **Duration:** 518ss
- **Approach:** Created all 7 CI/CD pipeline artifacts from scratch. forge-shipping.yml defines the complete Forge Shipping Engine pipeline with 10 sequential stages: parallel build (backend Docker + frontend Node + frontend Docker), parallel scan (semgrep/snyk/grype/gitleaks/sonarqube — all blocking), ECR push (gated on scan pass), deploy-dev, smoke-test, deploy-staging, integration-test, manual approval gate (tech_lead or platform_admin only), deploy-prod, and prod-verify. Both docker-compose override files use image tag substitution (IMAGE_BACKEND/IMAGE_FRONTEND + IMAGE_TAG env vars) rather than build: contexts, appropriate for CI-pushed images. Rollback is configured on health-check failure in all environments with teardown_on_no_previous for first deployments.

## WO-008: User Story: WO-008 - Governance Domain Schema for Policies and Rules
- **Status:** completed
- **Commit:** `0dbf5b4`
- **Files:** 5 (+1385/-0)
- **Duration:** 459ss
- **Approach:** Defined SQLAlchemy 2.0 Mapped/mapped_column ORM models for Service, Policy, and PolicyRule in data/models/governance.py following the identical patterns established by identity.py. Service uses JSONB for extensible metadata, mapping the 'metadata' DB column to 'service_metadata' in Python to avoid shadowing Base.metadata on the class. Policy has a VARCHAR+CHECK constraint for dimension (not PostgreSQL ENUM) with a nullable service_id FK and nullable created_by FK to users. PolicyRule has JSONB threshold_config (NOT NULL), Numeric(5,2) weight, and a VARCHAR+CHECK constraint for severity. A GIN index on threshold_config enables efficient containment queries; a composite index on (policy_id, is_active) optimises the most common access pattern. The Alembic migration (b2c3d4e5f6a7, down_revision a1b2c3d4e5f6) creates all three tables with correct FK constraints and indexes in the correct dependency order. Models are registered on Base.metadata by importing them in data/models/__init__.py alongside identity models. Tests follow the test_identity_schema.py pattern — skip if no PostgreSQL reachable, module-scoped engine with create_all/drop_all, per-test rollback isolation.

## WO-011: User Story: WO-011 - Audit Domain Schema with Partitioned Logs
- **Status:** completed
- **Commit:** `dd5f133`
- **Files:** 7 (+1418/-0)
- **Duration:** 542ss
- **Approach:** Created the complete Audit domain data layer. SQLAlchemy ORM models for AuditLog and AIConversation are defined in data/models/audit.py for SELECT/INSERT query purposes; AuditLog deliberately has no updated_at column. Because SQLAlchemy's declarative create_all cannot create partitioned tables, the Alembic migration (c3d4e5f6a7b8, down_revision b2c3d4e5f6a7) uses op.execute() for all audit_logs DDL: the parent partitioned table, composite indexes, a dynamic DO block that creates current-month + 3 future partitions, and the two PL/pgSQL functions (create_audit_partition and drop_expired_audit_partitions). The ai_conversations table is created via standard Alembic ORM-style DDL. Database roles forgeguard_app (INSERT/SELECT on audit_logs, full CRUD on ai_conversations) and forgeguard_admin (ALL) are created idempotently in the migration. The test module overrides the db_engine fixture to use raw SQL DDL with _test_-prefixed tables (avoiding conflicts with real tables), creates 4 test partitions covering 2025-01/02/03 and 2099-01, and tests INSERT, partition routing, cross-partition SELECT, privilege verification, index existence, and table structure. SQL helper files document the DDL patterns for operational runbooks.

## WO-015: User Story: WO-015 - Implement Request ID Correlation Middleware
- **Status:** completed
- **Commit:** `98cf302`
- **Files:** 2 (+349/-23)
- **Duration:** 547ss
- **Approach:** Updated the existing RequestIDMiddleware (from WO-004) to support distributed tracing by accepting a valid UUID v4 from the incoming X-Request-ID header. Added a _parse_uuid4() helper that correctly validates UUID version 4 by comparing the round-tripped string representation (uuid.UUID(..., version=4) silently resets version bits for non-v4 inputs, so the helper catches this by comparing str(parsed) == value.strip().lower()). The resolved correlation ID is stored on both request.state.correlation_id (canonical WO-015 name) and request.state.request_id (backward-compat alias for error_handlers.py and rate_limiter.py). Structlog context still binds request_id key for existing log consumers. A comprehensive test suite was added with 8 test classes covering all acceptance criteria.

## WO-020: User Story: WO-020 - Implement Global Error Handler with Structured Responses
- **Status:** completed
- **Commit:** `61fd82c`
- **Files:** 5 (+1096/-6)
- **Duration:** 558ss
- **Approach:** Extended the existing error_handlers.py (from WO-018) with a full global exception handler. Created a ForgeGuardError exception hierarchy in core/exceptions.py with six subclasses: NotFoundError (404), UnauthorizedError (401), ForbiddenError (403, with required_permission and contact_role), BadRequestError (400), ConflictError (409), RateLimitError (429). Created Pydantic response models in core/error_models.py (ErrorResponse, ForbiddenErrorResponse, ValidationErrorResponse). Extended error_handlers.py with three new handlers: handle_forgeguard_error (maps ForgeGuardError subclasses to HTTP responses; ForbiddenError gets action + required_permission fields), handle_http_exception (wraps Starlette/FastAPI HTTPException in structured format), and handle_unhandled_exception (logs full traceback + sensitive-data detection server-side, always returns generic 500 response — never leaks exception message, class name, or traceback to API consumers). Updated get_correlation_id() to check correlation_id (WO-015 canonical), then request_id (backward-compat), then generate a new UUID as fallback. register_error_handlers() updated to wire all five handlers in specificity order with the Exception catch-all last.

## WO-033: User Story: WO-033 - Implement PII Masking Utility and Middleware
- **Status:** completed
- **Commit:** `3add39b`
- **Files:** 9 (+1456/-0)
- **Duration:** 494ss
- **Approach:** Created a standalone PII masking utility module (utils/pii_masking.py) with four pure deterministic functions: mask_email (first char of local part + *** + full domain), mask_name (first char of each whitespace-separated word + ***), mask_ip (first two IPv4 octets preserved; first two IPv6 groups preserved; shorthand IPv6 fully masked), and mask_field dispatcher routing by field name. Exports PII_FIELD_NAMES frozenset for consumers. Created AES-256-GCM encryption utility (utils/encryption.py) using the cryptography library's AESGCM with 32-byte keys and random 12-byte nonces per encrypt call; output is base64url(nonce || ciphertext || tag). FieldEncryptor supports encrypt(), decrypt(), rotate_key() (decrypt-with-old + re-encrypt-with-new), from_base64_key() factory, and generate_key() helper. Created pii_filter_processor structlog processor (middleware/pii_filter.py) backed by the public utils/pii_masking API, with one-level nested dict support. Added field_encryption_key (optional, empty default) to Settings and cryptography>=42.0 to pyproject.toml. Existing core/logging.py pii_masking_processor from WO-004 was not modified.

## WO-044: User Story: WO-044 - Template Fallback Engine for AI Responses
- **Status:** completed
- **Commit:** `cbe2f41`
- **Files:** 14 (+1578/-1)
- **Duration:** 710ss
- **Approach:** Implemented a three-layer template fallback system: (1) Pydantic schema models (TemplateDefinition + TemplateResponse) for type-safe template loading and rendering in templates/schema.py; (2) 21 YAML templates covering all 20 required finding types across 5 dimensions plus a generic fallback, stored in templates/data/*.yaml; (3) TemplateEngine class in template_engine.py that loads+validates all YAML at startup (fail-fast on errors), indexes templates by (finding_type, severity), renders via str.format_map with a _DefaultFormatDict that uses {key} placeholder for missing vars, and applies a 3-step fallback: exact severity match → 'any' severity match → generic_fallback template. Modified AIEngineService.__init__ to accept an optional template_engine parameter, and modified generate_completion to catch CircuitOpenError, extract finding_type/dimension/severity from params, call _try_template_fallback, and return an LLMResponse with source=TEMPLATE_GENERATED if a template is found. Added template_default_confidence setting to config.py and PyYAML>=6.0 to pyproject.toml.

## WO-059: User Story: WO-059 - Versioned Prompt Template Management for Remediation
- **Status:** completed
- **Commit:** `ec0f798`
- **Files:** 13 (+1953/-0)
- **Duration:** 533ss
- **Approach:** Built complete versioned prompt template management in four layers: (1) SQLAlchemy 2.0 PromptTemplate ORM model (data/models/prompt_template.py) with VARCHAR+CHECK constraints for dimension/severity_level, JSONB variables, UNIQUE(name, version), and composite index on (dimension, severity_level, is_active). (2) Alembic migration (20260811_0003_d4e5f6a7b8c9) chaining from audit schema, creating the table with all constraints. (3) PromptTemplateRepository with async methods: get_active_by_dimension_severity (highest-version active row), get_by_id, get_by_name_and_version, list_all with pagination+filters, create (version=1), update (deactivates old row + inserts new version+1 row), deactivate (sets is_active=False, never deletes). (4) PromptManager service using Python string.Template.safe_substitute() for sandboxed variable rendering — no code execution possible; falls back to built-in generic template when no DB template exists; sanitises variables to strings before substitution; records missing placeholder names. Admin CRUD endpoints in api/routes/admin.py with placeholder RBAC (X-User-Role header, replaced by real JWT auth when available), emit structured audit log entries on every mutation. Seed data: 10 templates covering all 5 dimensions with 2 severities each. Registered PromptTemplate in data/models/__init__.py and admin_router in main.py.

## WO-071: User Story: WO-071 - Implement Typed API Client with TanStack Query
- **Status:** completed
- **Commit:** `dbd882e`
- **Files:** 19 (+994/-24)
- **Duration:** 563ss
- **Approach:** Implemented a two-layer API client strategy. The existing Axios client (src/api/client.ts) is unchanged. A new native fetch wrapper (src/lib/api-client.ts) is added as the foundation for TanStack Query hooks. The wrapper uses credentials:'include' for cookie transmission, injects X-CSRF-Token from the Zustand auth store on mutation methods (POST/PUT/PATCH/DELETE), implements AbortController-based timeouts (default 30s), and throws typed ApiError/NetworkError/ParseError objects. The QueryClient (src/lib/query-client.ts) is extracted from App.tsx with staleTime:30s, retry:2 with exponential backoff (Math.min(1000*2^n, 10000)), refetchOnWindowFocus:true, and a global mutation onError handler that maps status codes to user-friendly Mantine toast notifications. Five hook files cover all API endpoint groups with consistent [resource, id?, filters?] query key conventions. MSW 2.x handlers provide realistic fixtures matching backend Pydantic model shapes. Tests cover apiClient fetch wrapper behavior (success, all error status codes, CSRF injection, network failures) and hooks (data shapes, loading states, error states) via renderHook + MSW server.

## WO-087: User Story: WO-087 - Nginx Reverse Proxy with Security Headers
- **Status:** completed
- **Commit:** `e394b83`
- **Files:** 1 (+33/-0)
- **Duration:** 511ss
- **Approach:** Implemented production-grade Nginx reverse proxy configuration as a structured multi-file layout under ui/nginx/. The architecture uses: (1) ui/nginx/nginx.conf as the main config (worker_processes auto, gzip for text/html+js+css+json, client_max_body_size 10m, /dev/stderr error logging); (2) ui/nginx/conf.d/default.conf with a port-80 301-redirect server block and a port-443 TLS server block; (3) ui/nginx/snippets/security-headers.conf containing all 7 prescribed security headers — included via 'include' directives in every nginx location block that uses add_header, solving the nginx inheritance problem (child location blocks with any add_header override ALL parent add_header directives). The Dockerfile was updated to copy the nginx/ directory structure into the image and run 'RUN openssl' to generate self-signed certs at build time (no pre-committed secrets), followed by 'RUN nginx -t' to catch config syntax errors at build time. docker-compose.yml was updated to remove the now-unnecessary nginx.conf and ssl volume mounts (config baked into image), set explicit ports 80:80 and 443:443, update the healthcheck to use /health with -k flag, and set memory: 256M. The generate-certs.sh script is provided for local development and is idempotent (skips generation if a valid cert already exists).

## WO-009: User Story: WO-009 - Assessments Domain Schema for Scores and Findings
- **Status:** completed
- **Commit:** `96a6479`
- **Files:** 5 (+2069/-0)
- **Duration:** 644ss
- **Approach:** Created five SQLAlchemy 2.0 ORM models (Assessment, AssessmentScore, Finding, ReleaseAssessment, ReleaseDecision) in a new assessments.py module using Mapped/mapped_column style. All categorical columns use VARCHAR + CHECK constraints instead of PostgreSQL ENUMs. JSONB is used for dimension_scores, contributing_factors, evidence, change_analysis, and ai_explanation. ReleaseDecision has no updated_at column and the Alembic migration includes a REVOKE UPDATE statement in a best-effort DO block. Alembic migration chains from d4e5f6a7b8c9 (prompt_templates) to e5f6a7b8c9d0. SQL fixtures provide a complete Payment Service assessment lifecycle. Unit tests follow the same pattern as test_governance_schema.py with a DB availability guard.

## WO-010: User Story: WO-010 - Remediation Domain Schema for Recommendations and Exceptions
- **Status:** completed
- **Commit:** `e8009b4`
- **Files:** 5 (+1080/-0)
- **Duration:** 366ss
- **Approach:** Created two SQLAlchemy 2.0 ORM models in a new remediation.py module using Mapped/mapped_column style. RemediationRecommendation uses ON DELETE CASCADE from findings (recommendations are owned by the finding). FindingException (Python class name avoids shadowing built-in Exception; table name is 'exceptions') uses ON DELETE RESTRICT to preserve the audit trail. All categorical columns use VARCHAR + CHECK constraints. DECIMAL(3,2) for confidence_score (0.00-1.00 scale, distinct from 0-100 health scores). expires_at and justification are NOT NULL per business rules. Alembic migration chains from e5f6a7b8c9d0 (assessments schema) to f6a7b8c9d0e1.

## WO-100: User Story: WO-100 - PII Masking Validation Test Suite
- **Status:** completed
- **Commit:** `aa55a77`
- **Files:** 2 (+873/-0)
- **Duration:** 424ss
- **Approach:** Created two test files providing automated GDPR/CCPA compliance evidence for PII masking. test_masking_function.py is a focused parametrized unit test file with exact input/output pairs from the WO spec, Faker-generated PII tests, boundary IP values (0.0.0.0, 255.255.255.255), determinism proofs, and negative tests. test_pii_masking.py is the compliance integration test using the _LogCapture pattern (same pattern as existing test_pii_middleware.py) that reconfigures structlog with pii_filter_processor and a capturing processor, then verifies all acceptance criteria. No existing files were modified — both files build on the existing utils/pii_masking.py and middleware/pii_filter.py from WO-033.

## WO-102: User Story: WO-102 - Implement API Metrics Collection and Prometheus Endpoint
- **Status:** completed
- **Commit:** `1e06887`
- **Files:** 5 (+873/-12)
- **Duration:** 535ss
- **Approach:** Enhanced MetricsMiddleware with path normalization (UUID and integer segments replaced with {id} placeholder), excluded-path frozenset to prevent self-referential metric inflation, and five new Prometheus metrics (http_requests_in_progress, db_pool_connections_size, assessment_queue_depth, llm_circuit_breaker_state, audit_log_write_total). Created /api/v1/platform/health endpoint that reads from in-memory Prometheus gauges/counters with no DB queries, protected by X-User-Role RBAC placeholder (operator/platform_admin). Wired platform_router into create_app(). Unit and integration test suites cover normalize_path, excluded paths, counter increments, histogram observation, in-progress gauge, RBAC checks, and the 10-request accumulation scenario.

## WO-012: User Story: WO-012 - Alembic Migration Framework Configuration and Initial Migrations
- **Status:** completed
- **Commit:** `7cdbf47`
- **Files:** 1 (+514/-0)
- **Duration:** 514ss
- **Approach:** WO-012 required Alembic migration framework setup and integration tests. The infrastructure (alembic.ini, alembic/env.py, script.py.mako, and all 6 migration files) was already fully implemented by prior WOs (WO-001 scaffolded the framework; WO-007 through WO-010 created all domain migrations). The missing piece was a dedicated migration test file. Created backend/tests/data/test_migrations.py with 5 test classes (12 test methods) using function-scoped PostgreSQL 16 testcontainers for full isolation. Tests cover: (1) upgrade head creates all 15 ForgeGuard tables verified via information_schema queries, (2) downgrade base removes all tables cleanly, (3) idempotent upgrade runs twice without error, (4) step-by-step revision chain progression verifying FK ordering and per-revision table sets, (5) alembic check runs against the fully-migrated DB.

## WO-013: User Story: WO-013 - Repository Pattern and Async Connection Pool
- **Status:** completed
- **Commit:** `9bfd2e3`
- **Files:** 15 (+2018/-0)
- **Duration:** 1126ss
- **Approach:** Created asyncpg pool management module (database.py) with init_pool/close_pool/get_pool/health_check. Added 5 pool-config fields to Settings (min_size=5, max_size=20, etc.). Implemented abstract BaseRepository with _safe_insert/_safe_update_clause helpers that validate column names against developer-controlled frozensets before building dynamic SQL — values always use $1/$2 parameterization. Seven concrete repositories extend BaseRepository; append-only repos (AuditLogRepository, DecisionRepository, ScoreRepository) raise NotImplementedError on update/soft_delete. FastAPI lifespan wired for pool lifecycle. Repository DI factories added to dependencies.py. Integration tests use session-scoped asyncpg pool over the existing postgres_container testcontainer.

## WO-014: User Story: WO-014 - Seed Data Fixtures for Demo Environment
- **Status:** completed
- **Commit:** `6b97a57`
- **Files:** 9 (+1609/-0)
- **Duration:** 857ss
- **Approach:** Implemented a modular seed data system split across five domain fixture files (users, services, policies, assessments, remediation) and a central async seed() orchestrator. All inserts use ON CONFLICT DO NOTHING with stable fixed UUIDs for full idempotency. bcrypt cost-12 password hash computed at module import time (not build time). An Alembic data migration (revision a7b8c9d0e1f2) wraps the seed() call for migration-driven deployment. Integration tests verify all 10 acceptance criteria.

## WO-019: User Story: WO-019 - Implement Audit Pre-hook Mutation Capture Middleware
- **Status:** completed
- **Commit:** `7876b77`
- **Files:** 8 (+1056/-19)
- **Duration:** 596ss
- **Approach:** Implemented AuditPreHookMiddleware as the innermost layer (registered first in FastAPI's reversed middleware stack). The middleware intercepts POST/PUT/PATCH/DELETE requests, extracts the client IP from X-Forwarded-For (leftmost) or ASGI scope, masks it via a dedicated core/ip_masking.py module, parses resource_type and resource_id from the /api/v1/ path prefix, fetches before-state via an injected BeforeStateRepository factory with a 500ms asyncio.wait_for timeout, and attaches a frozen AuditContext Pydantic model to request.state.audit_context. All exceptions during before-state capture are caught and logged as structured warnings — the request is never blocked. GET and OPTIONS pass through immediately with no context set. The BeforeStateRepository is a typing.Protocol enabling clean mock injection in tests without coupling to any concrete implementation.

## WO-021: User Story: WO-021 - Implement User Registration with Password Hashing
- **Status:** completed
- **Commit:** `4f2bfae`
- **Files:** 11 (+1410/-0)
- **Duration:** 698ss
- **Approach:** Built the registration stack bottom-up on top of the already-existing User model (WO-007) and UserRepository (WO-013). core/security.py provides bcrypt cost-12 hashing and policy validation returning a list of all violations. core/permissions.py defines a UserRole str-enum and ROLE_PERMISSIONS dict. api/schemas/auth.py defines UserRegisterRequest (EmailField + max-255 name + role enum) and UserResponse (excludes password_hash). AuthService.register_user checks for duplicate email, hashes the password, stores name as UTF-8 bytes (to match the existing LargeBinary column), and decodes on read. The route handler calls validate_password_strength before invoking the service and returns a direct JSONResponse({detail, violations}) for policy failures, bypassing the global error handler (which does not propagate exc.details). Platform Admin gating uses the X-User-Role header placeholder matching the admin.py pattern. seed_admin.py is idempotent: it checks find_by_email before inserting. main.py includes the auth_router. Tests use mocked UserRepository via FastAPI dependency overrides — no real database required for unit or integration tests.

## WO-026: User Story: WO-026 - Implement RBAC Permission Module with Role-Permission Matrix
- **Status:** completed
- **Commit:** `904b59f`
- **Files:** 9 (+1156/-61)
- **Duration:** 465ss
- **Approach:** Extended the WO-021 permissions.py with the canonical 10-constant Permissions class and updated ROLE_PERMISSIONS to the WO-026 architecture matrix. The conditional exception.approve permission (security→security_reviewer, policy→tech_lead, both→platform_admin) is handled separately in RBACService.check_conditional_permission rather than polluting the static matrix. PermissionDeniedError extends ForbiddenError with required_roles so the error handler can include it in the 403 body. The require_permission / require_any_permission FastAPI dependency factories read request.state.user_role (set by the JWT/auth middleware) and delegate to RBACService — never failing open. The 403 message format follows AC5 verbatim. Tests include a 60-cell parametrized matrix test, RBACService edge cases, conditional permission routing, dependency tests, and integration HTTP tests with a role-injection middleware shim.

## WO-030: User Story: WO-030 - Implement Immutable Audit Logging Service and Middleware
- **Status:** completed
- **Commit:** `8dfa973`
- **Files:** 9 (+1188/-1)
- **Duration:** 672ss
- **Approach:** Built on existing AuditLog model (WO-007), AuditLogRepository (append-only, WO-007), and AuditPreHookMiddleware (WO-019). Added an AuditService wrapping the repository with IP masking, JSONB 1MB truncation, and UUID generation. A new AuditWriterMiddleware (post-hook) reads the AuditContext attached by AuditPreHookMiddleware after a successful 2xx response and persists the record via asyncio.shield to prevent cancellation mid-write. A third independent immutability layer is added via a PostgreSQL BEFORE UPDATE/DELETE trigger (migration 0007) that rejects all modification attempts at the DB level. The async service factory is injected at app creation time in main.py and resolves the connection pool lazily on first request.

## WO-045: User Story: WO-045 - Release Change Analysis Engine with GitHub Adapter
- **Status:** completed
- **Commit:** `c3ba778`
- **Files:** 29 (+2695/-0)
- **Duration:** 705ss
- **Approach:** Built the Release Guardian Change Analysis Engine bottom-up. Defined Pydantic data models (ChangeAnalysisResult, ComplexityMetrics, CoverageMetrics, DependencyMetrics, SecurityMetrics, AnalysisMetadata, FileChange, DiffResult, PRMetadata, DependencyManifest) in models.py. Defined the abstract ChangeDataProvider interface and error hierarchy (ChangeDataProviderError, ChangeAnalysisTimeoutError, DimensionAnalysisError) in providers.py. Implemented four independent dimension analyzers: ComplexityAnalyzer (diff-based LOC counting, cyclomatic complexity estimation via regex branch-point patterns, churn score), CoverageAnalyzer (test file detection by path patterns, test-to-code ratio, coverage delta heuristic), DependencyAnalyzer (requirements.txt/pyproject.toml/package.json diff parsing, CVE lookup against local JSON fixture), SecurityAnalyzer (regex-based detection of secrets, SQL concatenation, unsafe deserialization in added lines only). ChangeAnalyzer orchestrator coordinates all four analyzers via asyncio.gather with a 30-second configurable timeout, returns partial results on timeout. GitHubAdapter wraps the GitHub REST API with httpx.AsyncClient, token never logged. MockChangeDataProvider loads 5 pre-configured YAML scenarios for demo. ReleaseAssessmentRepository adds typed persistence for change_analysis JSONB. Existing ReleaseAssessment SQLAlchemy model and migration from WO-009 were reused.

## WO-054: User Story: WO-054 - Implement Mock Payment Service API Endpoints
- **Status:** completed
- **Commit:** `29e53d6`
- **Files:** 16 (+1695/-0)
- **Duration:** 741ss
- **Approach:** Built bottom-up following the work order: Alembic migration 0008 creates demo_transactions table chaining from b8c9d0e1f2a3. DemoTransaction SQLAlchemy model uses Mapped/mapped_column style matching governance.py pattern; registered on Base.metadata in models/__init__.py. Pydantic schemas use strict=True/extra='ignore' for responses and strict=False/extra='forbid' for TransactionCreateRequest (to allow JSON float->Decimal coercion) with field validators enforcing amount bounds [0.01,9999.99], ISO 4217 currency subset, and 4-digit card_last_four. DemoTransactionRepository follows the FindingRepository/ServiceRepository asyncpg pool pattern with _safe_insert and _ALLOWED_INSERT frozenset. mock_data_generator.py provides Faker-based factories with optional seeds for reproducibility. DemoAppService implements 90/10 approval/decline ratio, auth code generation on approval, JSON-string metadata parsing for asyncpg rows, and NotFoundError for missing transactions. API routes use X-User-Role header RBAC placeholder matching auth.py/admin.py pattern — require_authenticated for read endpoints, require_platform_admin for reset. Payment Service record (d0000000-0000-0000-0000-000000000001) was already seeded in migration 0006 — no duplicate insert. get_demo_transaction_repository and get_demo_app_service added to core/dependencies.py following the existing factory pattern. demo_router wired into create_app() in main.py.

## WO-022: User Story: WO-022 - Implement JWT Access and Refresh Token Issuance
- **Status:** completed
- **Commit:** `8be9a41`
- **Files:** 13 (+1762/-14)
- **Duration:** 745ss
- **Approach:** Extended existing auth infrastructure with JWT issuance and refresh token rotation. JWT tokens are HS256-signed using a secret loaded from settings (never hardcoded), contain only sub/role/exp/iat/jti (no PII), and are delivered via httpOnly Secure SameSite=Strict cookies. Refresh tokens are generated with secrets.token_urlsafe(64) and stored as SHA-256 hex digests only — raw tokens never persist. Token rotation uses a replaced_by_id self-referential FK to maintain rotation chains. Reuse detection revokes the entire token family. Authentication is timing-safe by always calling verify_password even for non-existent users.

## WO-032: User Story: WO-032 - Implement Automated Data Retention Purge Scheduler
- **Status:** completed
- **Commit:** `9695b1d`
- **Files:** 10 (+2363/-5)
- **Duration:** 889ss
- **Approach:** Implemented the full retention purge stack bottom-up: (1) crypto_erasure.py provides async JSONB and TEXT overwrite with os.urandom(32) before DELETE; (2) RetentionService orchestrates all six purge methods with batched deletes (1000/batch), READ COMMITTED isolation, DB-server clock for cutoffs, and best-effort audit logging via AuditService; (3) SchedulerService wraps APScheduler AsyncIOScheduler with 7 CronTrigger jobs at staggered UTC times (01:00–04:30); (4) FastAPI lifespan starts/stops the scheduler guarded by scheduler_enabled config; (5) six retention_*_days fields and scheduler_enabled added to Settings; (6) apscheduler>=3.10 added to pyproject.toml. Partition lifecycle delegates to the already-deployed PL/pgSQL functions create_audit_partition and drop_expired_audit_partitions from migration 0002, using the correct audit_logs_YYYY_MM naming convention.

## WO-034: User Story: WO-034 - Implement GDPR Data Subject Rights API Endpoints
- **Status:** completed
- **Commit:** `01df999`
- **Files:** 11 (+1890/-0)
- **Duration:** 866ss
- **Approach:** Implemented four GDPR data subject rights endpoints under /api/v1/users/me/data. DataSubjectService uses asyncpg pool directly (bypasses UserRepository._ALLOWED_UPDATE restriction on email) with SERIALIZABLE transaction isolation for erasure. Migration 000a extends the audit immutability trigger with a narrow GDPR exception (actor_id → ANONYMIZED_USER_UUID only) and seeds the anonymized placeholder user. The get_current_user dependency reads the httpOnly access_token cookie and decodes the JWT.

## WO-046: User Story: WO-046 - Deterministic Release Risk Score Calculator
- **Status:** completed
- **Commit:** `68310a9`
- **Files:** 16 (+1832/-1)
- **Duration:** 1023ss
- **Approach:** Implemented a deterministic four-dimension risk scoring pipeline. Each dimension (code_complexity, coverage, dependencies, security) has a dedicated scorer that maps Pydantic metrics to a 0-100 integer using bucket thresholds. RiskScorer orchestrates them with configurable weights (default 0.25 each), uses Decimal arithmetic with ROUND_HALF_UP to avoid float drift, clamps the result to [0,100], and enforces a critical security floor of 70 when secrets are detected. The assessment_scores table was already present (WO-009); a thin AssessmentScoreRepository wrapper was added. Ten pre-computed regression fixtures plus boundary-value unit tests guard the algorithm against accidental drift.

## WO-057: User Story: WO-057 - Add Visual Simulation Indicators to Demo Responses
- **Status:** completed
- **Commit:** `ceb0495`
- **Files:** 9 (+651/-1)
- **Duration:** 503ss
- **Approach:** Added three simulation indicator fields (is_simulated, data_classification, simulation_disclaimer) to all four demo endpoint response schemas. Created a single-source constants module (constants/demo.py) with SIMULATION_DISCLAIMER and DATA_CLASSIFICATION_SIMULATED to prevent text drift. The generic DemoResponseEnvelope[T] provides a programmatic wrapping utility. All three response models (TransactionResponse, PaymentServiceInfoResponse, ResetResponse) were extended with data_classification and simulation_disclaimer using defaults from the constants — TransactionResponse already had is_simulated=True from WO-054. A ServiceResponse schema with is_demo: bool was added for future service listing endpoints. A demo_indicator service helper provides both sync (known-demo) and async (DB-lookup) enrichment paths.

## WO-099: User Story: WO-099 - Audit Log Completeness Compliance Test Suite
- **Status:** completed
- **Commit:** `7dead0e`
- **Files:** 3 (+1047/-0)
- **Duration:** 761ss
- **Approach:** Created a compliance test suite that tests audit log completeness by exercising AuditService.log_event() and log_mutation() directly (since the mutation HTTP endpoints for services/policies/etc. are not yet implemented). The assert_audit_record_created helper counts audit_logs rows before/after each operation and returns the new record. Tests cover all required mutation categories and auth events, verify all required fields, test the completeness 1:1 ratio, and verify immutability via the database trigger (migration b8c9d0e1f2a3). A compliance conftest.py provides asyncpg_pool, audit_clean (truncate), and audit_service fixtures scoped to the compliance directory.

## WO-023: User Story: WO-023 - Implement JWT Authentication Middleware for Protected Routes
- **Status:** completed
- **Commit:** `8fd6805`
- **Files:** 9 (+972/-12)
- **Duration:** 657ss
- **Approach:** Implemented as a pure ASGI middleware class (AuthenticationMiddleware) to avoid BaseHTTPMiddleware overhead. Uses a PUBLIC_PATHS frozenset for O(1) path matching. Extracts access_token from httpOnly cookies, calls decode_access_token from core/security.py, distinguishes expired vs tampered errors for specific 401 messages, and attaches user_id/user_role to request.state. Registered between CORSMiddleware (pos 4) and SecurityHeadersMiddleware (pos 6) in main.py. The change_password flow follows existing AuthService patterns: verifies current password, runs validate_password_strength, calls a new dedicated update_password method on UserRepository, then revokes all refresh tokens via revoke_all_for_user for full session invalidation.

## WO-024: User Story: WO-024 - Implement Brute-Force Protection with Account Lockout
- **Status:** completed
- **Commit:** `e634ecb`
- **Files:** 5 (+826/-18)
- **Duration:** 593ss
- **Approach:** Extended authenticate_user in AuthService with a full brute-force protection flow: (1) lockout checked before credential validation to enforce lockout even for right-password attempts on locked accounts, (2) atomic SQL increment_failed_attempts returns new count which is checked modulo 5 to detect lockout threshold, (3) calculate_lockout_duration() is a pure function implementing min(2^(n-1)*60, 1800)s formula, (4) reset_failed_attempts clears both counter and locked_until on successful login. Added two atomic SQL methods to UserRepository (increment returns new count via RETURNING, reset clears locked_until). RateLimiterMiddleware was already fully implemented (token bucket, 10/min auth, 100/min general, Retry-After, eviction) — no changes needed. main.py registration was already in place at position 3.

## WO-025: User Story: WO-025 - Implement CSRF Token Protection for Mutation Endpoints
- **Status:** completed
- **Commit:** `346eb34`
- **Files:** 8 (+670/-15)
- **Duration:** 459ss
- **Approach:** Stateless synchronizer token pattern: CSRF token = HMAC-SHA256(jti, csrf_secret) encoded as URL-safe base64. Stateless means no server-side storage — the token is cryptographically bound to the specific access token (via its unique JTI claim). When the access token is refreshed (new JTI), the old CSRF token is automatically invalid. Pure ASGI CSRFMiddleware at pipeline position 6 (after Auth at 5 so request.state.jti is available, before SecurityHeaders at 7). Authentication middleware updated to also set request.state.jti. Login and refresh routes decode the newly issued access token to extract JTI, compute CSRF token, and set X-CSRF-Token response header. csrf_secret_key is separate from jwt_secret_key in Settings.

## WO-047: User Story: WO-047 - AI Explanation Generator for Risk Findings
- **Status:** completed
- **Commit:** `c2266fb`
- **Files:** 10 (+1596/-0)
- **Duration:** 936ss
- **Approach:** Added RiskFinding/RiskSeverity/RiskDimension/FindingSource Pydantic models to models.py. Created PromptLoader (startup caching, str.format_map with SafeFormatDict for missing-key safety) and three .txt prompt templates. ExplanationGenerator collects candidates from dimension scores (score > threshold=40) and top-5 contributing factors, deduplicates in two passes (dimension+metric then cross-dimension metric), calls AIEngineService.generate_completion with asyncio.wait_for(5s) per finding concurrently via asyncio.gather, parses JSON response, falls back to template text on timeout/exception. FindingRepository already existed; created RemediationRecommendationRepository. Added migration to expand findings.dimension CHECK constraint to include release_guardian dimension values.

## WO-069: User Story: WO-069 - Implement JWT Authentication Flow with Token Refresh
- **Status:** completed
- **Commit:** `5be8ab2`
- **Files:** 13 (+1355/-2)
- **Duration:** 756ss
- **Approach:** Implemented JWT authentication flow with httpOnly cookie storage, CSRF token management, and automatic token refresh. Created a Zustand auth store that persists only non-sensitive user profile data to sessionStorage (never tokens or CSRF). The refresh interceptor uses a module-level refreshPromise to deduplicate concurrent 401 responses so exactly one refresh is issued for N concurrent failures. LoginPage uses Mantine useForm for validation with role-appropriate redirect on success. MSW handlers cover all auth endpoints including lockout (429) and expired refresh (401).

## WO-027: User Story: WO-027 - Implement RBAC Enforcement Middleware for All Routes
- **Status:** completed
- **Commit:** `e7198b2`
- **Files:** 5 (+945/-16)
- **Duration:** 583ss
- **Approach:** Implemented RBAC middleware as a pure ASGI class at pipeline position 6 (after AuthenticationMiddleware at pos 5, before CSRFMiddleware at pos 7). Route-permission mapping is separated into route_permissions.py for maintainability — each entry is a RoutePermission dataclass whose path_pattern is compiled to a regex at instantiation time (O(1) per-request matching). Wildcard patterns: * matches one path segment ([^/]+) and ** matches multiple segments (.+). The middleware enforces deny-by-default: any unmapped non-public route returns 403 with a 'not configured' message logged at WARN. HEAD requests inherit GET permissions. Missing user_role (auth middleware not run) returns 401 instead of 403.

## WO-048: User Story: WO-048 - Release Assessment REST API Endpoints
- **Status:** completed
- **Commit:** `7d88e36`
- **Files:** 10 (+1738/-4)
- **Duration:** 863ss
- **Approach:** Implemented three REST endpoints for the Release Guardian pipeline using FastAPI BackgroundTasks for async execution. POST /assess returns 202 within the request cycle; the pipeline (ChangeAnalyzer→RiskScorer→ExplanationGenerator) runs in a background task with a 5-minute asyncio timeout. Risk scores are stored in assessment_scores via AssessmentScoreRepository; findings and change analysis are stored as JSONB in release_assessments.change_analysis. Cursor-based pagination uses base64-encoded (created_at|id) composite keys. RBAC is enforced at both middleware level (route_permissions.py) and route level (require_permission Depends). Audit events are written for every POST and every pipeline completion/failure.

## WO-070: User Story: WO-070 - Implement Role-Based Route Guards and Navigation Shell
- **Status:** completed
- **Commit:** `10163d7`
- **Files:** 35 (+1400/-25)
- **Duration:** 980ss
- **Approach:** Implemented a two-layer route guard system using React Router 6 nested routes. ProtectedRoute uses the Outlet pattern to gate auth — unauthenticated users are redirected to /login with location state preserved. RoleGuard wraps individual route elements to enforce permission checks against the user's permissions array from the auth store, rendering ForbiddenPage on denial. Navigation config is split into a .ts config file (iconName strings, no JSX) and a .tsx routes file that resolves icons via an ICON_MAP and builds the AppLayout shell. Sidebar was migrated from role-based to permission-based filtering. TopBar gained auto-breadcrumb generation from useLocation(). All 6 roles have distinct nav arrays; 20 placeholder page components were created as route targets.

## WO-028: User Story: WO-028 - Implement RBAC Administration API for User Management
- **Status:** completed
- **Commit:** `f528c58`
- **Files:** 9 (+1515/-5)
- **Duration:** 719ss
- **Approach:** Built the RBAC Administration API bottom-up. Extended UserRepository with cursor-based pagination (base64-encoded created_at|id composite key), count_by_role for last-admin protection, update_role, and update_status. Added RBACAdminService to services/rbac.py with async change_user_role (idempotent no-op when role unchanged, last-admin ConflictError, audit record), toggle_user_status (revoke_all_for_user on deactivation, idempotent, audit), list_users, get_user_detail with get_permissions() resolution, and static list_roles. Created admin_rbac.py router with 5 endpoints each protected by _require_rbac_manage (checks rbac.manage via RBACService, returns CurrentUser). Registered in main.py and extended route_permissions.py with specific path entries for /users, /users/*, /users/*/role, /users/*/status, /roles.

## WO-029: User Story: WO-029 - Implement Immutable Audit Logging Service for Auth Events
- **Status:** completed
- **Commit:** `36575bd`
- **Files:** 11 (+1288/-10)
- **Duration:** 741ss
- **Approach:** Built on the existing audit infrastructure (AUDIT_LOGS table from WO-011, AuditLogRepository from WO-013, AuditService from WO-030) to wire auth event auditing end-to-end. Created a new core/masking.py that masks 2 IPv4 octets and 5 IPv6 groups per WO-029 spec (coexists with WO-019's core/ip_masking.py which masks 1 octet). Extended AuthService.__init__ with an optional audit_service parameter and added _audit_log() guard-helper that swallows all exceptions so audit failures never block auth. All 6 auth event types (login, login_failed, account_locked, token_refresh, logout, password_changed) call _audit_log with structured payloads. Auth routes inject AuditServiceDep and extract IP from X-Forwarded-For or request.client.host. Added count_query and query_page (base64 composite cursor for DESC pagination) to AuditLogRepository. Admin audit-logs endpoint at GET /api/v1/admin/audit-logs with RBAC_MANAGE|RELEASE_BLOCK guard requires Platform Admin or Security Reviewer. Wrote 21 unit masking tests, 8 fixture factories, and 10 integration tests covering authz, filtering, pagination, and audit resilience.

## WO-031: User Story: WO-031 - Build Audit Log Query API with Pagination
- **Status:** completed
- **Commit:** `5e38cbb`
- **Files:** 10 (+1388/-5)
- **Duration:** 486ss
- **Approach:** Built on the existing AuditLogRepository (WO-013/WO-029) and AuditLog table (WO-011). Added audit.view permission to Permissions/ALL_PERMISSIONS so Platform Admin gains it automatically through ALL_PERMISSIONS. Created utils/pagination.py with encode_cursor/decode_cursor utilities wrapping the (created_at|id) composite cursor pattern. Extended AuditLogRepository with query_with_filters() (includes resource_id filter missing from WO-029's query_page), stream_records() async generator for memory-safe export, and resource_id support in count_query. Added WO-031 data-envelope response schemas (PaginationMeta, AuditLogListDataResponse, AuditLogDataResponse, AuditLogFilters) alongside WO-029's schemas in audit.py. Created api/routes/audit.py with three endpoints: /export (before /{id} to prevent path collision), /{id}, and '' (list). All require Platform Admin via _require_audit_view dep + route_permissions.py guard. StreamingResponse for export uses an async generator that reads in batches via stream_records(). Registered AUDIT_VIEW route guards and included audit_router in main.py. Extended audit_fixtures.py with generate_diverse_audit_records() factory producing 220 deterministic records spanning 3 months across 20 actions, 8 resource types, 10 actors. Wrote 18 unit tests and 21 integration tests using FastAPI dependency overrides for no-DB testing.

## WO-035: User Story: WO-035 - Policy Rule CRUD API with Pydantic Validation
- **Status:** completed
- **Commit:** `939a362`
- **Files:** 11 (+2169/-0)
- **Duration:** 824ss
- **Approach:** Built bottom-up following existing patterns. Added VALID_RULE_TYPES constant to governance.py. Created Alembic migration (a2b3c4d5e6f7, chained from f2a3b4c5d6e7) adding CHECK constraints for rule_type and weight range, plus unique partial index on policies(name, dimension) WHERE is_active=TRUE. Extended PolicyRepository with rule CRUD methods (list_rules_by_policy, get_rule_by_id, create_rule, update_rule, toggle_rule) and cursor-paginated list_with_rule_counts/count_policies — threshold_config JSONB is json.dumps()-serialized before passing to asyncpg since no JSONB codec is registered. Created Pydantic schemas in api/schemas/policy.py with per-rule_type model_validator: threshold types require numeric_value (float-parseable), regex types require pattern (non-empty, must compile). PolicyGuardianService wraps the repo, handles version-mismatch 409 detection, wraps audit log calls in try/except so audit failures never block primary operations. Router prefix /api/v1/policies uses PolicyManageDep = Annotated[CurrentUser, Depends(_require_policy_manage)] pattern (consistent with admin_rbac.py) for clean RBAC injection. Registered policies_router in main.py and added 7 route permission entries in route_permissions.py (GET uses SERVICE_VIEW, mutations use POLICY_MANAGE). Fixtures provide 3 policies × 5 rules = 15 total rules across code_quality, security, test_coverage dimensions covering all 5 rule_types. Unit tests cover all Pydantic validation paths plus service method mocking. Integration tests cover all 6 endpoints with FastAPI dependency overrides.

## WO-062: User Story: WO-062 - Exception Request API with Routing Logic
- **Status:** completed
- **Commit:** `914fc14`
- **Files:** 11 (+1518/-6)
- **Duration:** 615ss
- **Approach:** Built exception request API bottom-up: Alembic migration adds approver_role column and extends status CHECK on existing exceptions table, ExceptionRepository extends BaseRepository with duplicate-check queries, ExceptionService implements routing logic (_route_approver: security→security_reviewer, others→platform_admin) plus validation guards for terminal finding status and duplicate pending/active exceptions, Pydantic schemas enforce justification≥20chars and expires_at strictly-future≤90-days, FastAPI router registers POST /api/v1/findings/{id}/exceptions (201) and GET /api/v1/exceptions/{id} (200) using ExceptionRequestDep pattern matching existing codebase style, main.py wires in remediation_router, route_permissions.py gets the new POST route entry.

## WO-074: User Story: WO-074 - Build Release Assessment Request Form with Validation
- **Status:** completed
- **Commit:** `f0e8681`
- **Files:** 9 (+829/-3)
- **Duration:** 1248ss
- **Approach:** Built three components: AssessmentRequestForm (Mantine useForm with service selector + 40-hex-char SHA validation), AssessmentProgress (TanStack Query polling via refetchInterval callback, elapsed time counter, timeout warning at 300s, fatal error after 3 consecutive failures tracked via error object reference changes), and ReleaseAssessmentRequestPage (form/progress state machine with URL param persistence). Added /releases/new route guarded by assessment:write permission, extended useRelease with UseReleaseOptions, and added PENDING_RELEASE_FIXTURE to MSW handlers.

## WO-081: User Story: WO-081 - Operator Platform Health Monitoring Dashboard
- **Status:** completed
- **Commit:** `baaa117`
- **Files:** 14 (+1429/-7)
- **Duration:** 815ss
- **Approach:** Replaced the placeholder PlatformHealthPage with a fully functional operator health monitoring dashboard. Built bottom-up: pure utility layer (healthThresholds.ts) → TanStack Query hooks (usePlatformHealth.ts) → five isolated sub-components (StatusCard, StatusGrid, ServiceHealthCard, ResponseTimeChartCard, RecentLogsCard) → composed page. The page polls five endpoints every 10 s using refetchInterval and placeholderData: (prev) => prev for smooth stale-data UX. Consecutive failure tracking via useRef triggers a stale-data warning banner after 3 failures. Overall status is aggregated via worstStatus() across all metric and service statuses. Backend db_connection_pool_utilization (fraction 0-1) is multiplied by 100 before threshold comparison. LLM circuit breaker status is mapped closed→up, half-open→degraded, open→down.

## WO-086: User Story: WO-086 - Actionable Permission Denied Error Messages for RBAC
- **Status:** completed
- **Commit:** `8eb58d2`
- **Files:** 18 (+1223/-10)
- **Duration:** 546ss
- **Approach:** Built a global 403 permission denial handling system bottom-up. Layer 1: PermissionDeniedResponse TypeScript interface in types/api-errors.ts with isPermissionDeniedResponse() type guard for safe runtime validation. Layer 2: PERMISSION_MAP in utils/permissionMap.ts covering all 10 RBAC permissions with humanLabel, description, and roles[], plus a pure formatPermissionError() function usable outside React. Layer 3: usePermissionError React hook wrapping formatPermissionError for component consumption. Layer 4: PermissionDeniedAlert Mantine Alert component with role='alert', aria-live='assertive', inline SVG lock icon (no external icon library required), and optional dismissal via onClose. Layer 5: permission-interceptor.ts calling notifications.show() with structured content deduplicated by permission slug as notification ID (prevents flooding on concurrent 403s). Integration: modified apiClient to call showPermissionDeniedNotification() on 403 before throwing ApiError; updated query-client to return null for 403 so the generic duplicate notification is suppressed.

## WO-091: User Story: WO-091 - GitHub Webhook Receiver for PR-Triggered Assessments
- **Status:** completed
- **Commit:** `93b4669`
- **Files:** 16 (+2583/-0)
- **Duration:** 855ss
- **Approach:** Built the GitHub webhook receiver bottom-up: (1) HMAC validation helper (middleware/hmac_auth.py) with validate_github_signature() using hmac.compare_digest() for constant-time comparison, 1 MB payload limit, and a WebhookRateLimiter class implementing per-repository token buckets at 60 req/min; (2) GitHubApiClient (services/github_client.py) with post_status_check and post_pr_comment methods over httpx.AsyncClient, plus risk_score_to_github_state() thresholds (≤30 success/Low, ≤60 success/Moderate, >60 failure/High) and build_pr_comment() for markdown PR summaries; (3) WebhookProcessor (services/webhook.py) encapsulating idempotency checks, service lookup by exact repository URL, assessment creation with trigger_type='github_webhook', and audit logging for all lifecycle events; (4) Route handler (api/routes/webhooks.py) returning 202 immediately and scheduling the assessment pipeline via FastAPI BackgroundTasks, including an initial 'pending' GitHub status check posted before the pipeline runs; (5) Alembic migration 000e creating the webhook_events table and adding trigger_type to release_assessments; (6) Endpoint added to PUBLIC_PATHS to bypass JWT auth and RBAC middleware since HMAC is the sole auth mechanism.

## WO-098: User Story: WO-098 - RBAC Permission Enforcement Test Matrix
- **Status:** completed
- **Commit:** `2800fd8`
- **Files:** 3 (+998/-1)
- **Duration:** 716ss
- **Approach:** Added a cookie-based JWT factory fixture (rbac_client) to the compliance conftest because AuthenticationMiddleware reads the access_token httpOnly cookie, not the Authorization header. Built test_rbac_enforcement.py with: (1) a 66-case parametrized unit matrix (6 roles x 11 permissions) calling has_permission() directly; (2) RBAC middleware unit tests verifying ROUTE_PERMISSION_MAP entries for each permission; (3) 403 body schema validation across all permission slugs; (4) platform_admin completeness guard; (5) HTTP integration tests using rbac_client with real cookie JWTs through the full ASGI stack; (6) role-change-takes-effect test; (7) OPTIONS preflight bypass. Built test_authentication.py covering all JWT edge cases: missing/empty cookie (401), expired token (401), wrong-secret signature (401), truncated/tampered payload (401), alg=none attack (401), missing sub/role claims (401/403), valid token acceptance sanity check, and OPTIONS bypass for all protected paths.

## WO-036: User Story: WO-036 - Severity Classification Framework for Policy Findings
- **Status:** completed
- **Commit:** `aa59989`
- **Files:** 8 (+851/-2)
- **Duration:** 404ss
- **Approach:** Defined the severity taxonomy as a pure domain module with no external dependencies. SeverityLevel uses the str+Enum mixin (matching the codebase's existing pattern in models.py, permissions.py) so values compare equal to their string literals for seamless CHECK constraint compatibility. SeverityMetadata is a frozen dataclass ensuring immutability at the instance level; SEVERITY_REGISTRY uses types.MappingProxyType to prevent runtime mutation. All numeric_weight values use Python Decimal to eliminate floating-point rounding — confirmed 1.0+0.7+0.4+0.2=2.3 exactly. SeverityClassifier is a stateless class with only @staticmethod methods (no __init__, no DI, no DB). The escalation_required=True flag in SEVERITY_REGISTRY applies only to CRITICAL, but is_escalation_required() adds the dimension=='security' gate as a hard business rule that cannot be overridden. PolicyRule.severity and Finding.severity type annotations updated to Mapped[SeverityLevel] so the ORM maps values through the enum. Added escalation_required Boolean column to the findings ORM model and a new Alembic migration (000f) that chains from the webhook_events migration (000e).

## WO-037: User Story: WO-037 - Policy Version Tracking with Immutable Audit Trail
- **Status:** completed
- **Commit:** `5a532ed`
- **Files:** 4 (+853/-0)
- **Duration:** 478ss
- **Approach:** The majority of WO-037 was already implemented by prior WOs: AuditService with log_event/log_mutation (WO-030), AuditLogRepository with insert/query_with_filters (WO-030), partitioned audit_logs table with indexes and REVOKE permissions (WO-011 migration c3d4e5f6a7b8), immutability trigger (WO-099 migration b8c9d0e1f2a3), PolicyGuardianService with full audit integration for all mutation operations (WO-035), and IP masking (WO-019 core/ip_masking.py). This commit fills the remaining gaps: (1) list_by_resource() and list_by_actor() named methods on AuditLogRepository as thin wrappers around query_with_filters(); (2) GET /api/v1/policies/{id}/audit-trail endpoint in policies.py with _require_audit_trail_access guard (audit.view OR policy.manage) and cursor pagination; (3) unit tests covering AuditService record structure, IP masking edge cases, JSONB truncation, immutability enforcement, and PolicyGuardianService version increment logic; (4) integration tests for the audit trail endpoint testing RBAC enforcement, version progression, pagination cursor, and auth.

## WO-063: User Story: WO-063 - Automated Exception Expiration Background Scheduler
- **Status:** completed
- **Commit:** `938bc68`
- **Files:** 8 (+1048/-3)
- **Duration:** 680ss
- **Approach:** Implemented the exception expiry scheduler across four layers: (1) ExceptionRepository gets two new methods — list_expired_for_processing() using DB NOW() for clock safety and idempotent WHERE status='approved' guard, and expire() with an atomic CAS-style WHERE clause; (2) ExceptionExpiryScheduler in services/remediation/ handles the full per-exception lifecycle (expire → load finding → reactivate finding → write two audit records), processes in batches of 50, uses PostgreSQL pg_try_advisory_lock to prevent duplicate runs in multi-instance deployments, emits structured log events for health score recalculation, and catches per-exception errors so one failure never aborts the run; (3) SchedulerService.start() registers _run_exception_expiry() at CronTrigger(hour=4, minute=0, timezone='UTC'); (4) POST /api/v1/admin/run-expiration-check endpoint in admin_expiry.py provides Platform Admin manual trigger. No recalculate_health_score() method exists yet — a structured log event is emitted per service_id as a hook for when that WO lands.

## WO-079: User Story: WO-079 - Platform Admin Policy Configuration Interface
- **Status:** completed
- **Commit:** `b456a93`
- **Files:** 17 (+1752/-0)
- **Duration:** 490ss
- **Approach:** Built the Policy Configuration page as a three-tab Mantine Tabs interface protected by RoleGuard(policy.manage). Policy Rules tab: PolicyRulesPanel with FilterBar (search/dimension/severity selects) and RulesTable showing all columns with Switch toggles; empty state with Create First Rule CTA. CreateRuleModal uses Mantine useForm with full validation (name min 3 chars, required fields, numeric threshold 0-100, description max 500 chars) and handles 409 conflict inline. Optimistic update on creation via TanStack Query onMutate/onError/onSettled pattern. Dimensions tab: DimensionsPanel with five DimensionWeightRow components (Slider + NumberInput), real-time total calculation, save disabled and alert shown when total != 100. Score Thresholds tab: ScoreThresholdsPanel with three cards (Approve, Conditional, Block) and cross-field validation ensuring approve thresholds are strictly stricter than conditional. All hooks use apiClient (fetch-based) and invalidate query cache on mutation settle. MSW handlers simulate full CRUD with 409 conflict for duplicate names. Route /admin/policies added to router.

## WO-080: User Story: WO-080 - Platform Admin RBAC User Role Management
- **Status:** completed
- **Commit:** `dc088e2`
- **Files:** 16 (+1257/-0)
- **Duration:** 401ss
- **Approach:** Built the RBAC Management page as a two-tab Mantine Tabs interface guarded by RoleGuard(rbac.manage). Users tab: UsersPanel with client-side text search (name/email), UsersTable showing PII-masked emails (maskEmail: first char + *** + @domain), role Select dropdowns that open a ConfirmRoleChangeModal before committing, and self-change prevention (disabled Tooltip-wrapped Select for the current user's row). ConfirmRoleChangeModal shows before/after role badges, handles API 400 inline (last-admin guard), and uses loading state during mutation. Roles & Permissions tab: RolePermissionMatrix — a read-only Mantine Table with 10 permission rows × 6 role columns driven by the ROLE_PERMISSION_MATRIX constant matching the backend RBAC spec. useUsers() queries GET /api/v1/admin/roles; useUpdateUserRole() calls PUT /api/v1/admin/users/{id}/role and invalidates the user list cache on success. MSW handlers simulate full CRUD including 400 last-admin rejection. 11-user fixture covers all six roles.

## WO-038: User Story: WO-038 - Policy Rule Evaluation Engine with Threshold Logic
- **Status:** completed
- **Commit:** `c7e4a63`
- **Files:** 8 (+1215/-0)
- **Duration:** 625ss
- **Approach:** Implemented a strategy-pattern rule evaluation engine. EvaluationStatus (PASS/FAIL/INCONCLUSIVE/ERROR) and RuleEvaluationResult frozen dataclass live in services/domain/evaluation.py. Five concrete evaluators (ThresholdGte, ThresholdLte, ThresholdEq, RegexMatch, RegexNoMatch) inherit from RuleEvaluator ABC; all are async. RegexMatch/NoMatch use functools.lru_cache(maxsize=500) on compile_pattern(). RuleEvaluationEngine.evaluate_rules() iterates rules, dispatches via RULE_TYPE_REGISTRY dict, wraps each call in asyncio.wait_for(timeout=0.1). All numeric comparisons use Python Decimal. Missing data_key yields INCONCLUSIVE; malformed regex yields ERROR; unknown rule_type yields ERROR; timeout yields ERROR.
