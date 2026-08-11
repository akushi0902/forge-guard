# ForgeGuard

AI-powered Engineering Governance and Release Readiness platform.

ForgeGuard continuously evaluates application compliance against configurable engineering policies and analyses proposed code changes for release risk. It produces two explainable scores:

- **Engineering Health Score** (0–100) — *"Is this application following our engineering standards?"*
- **Release Risk Score** (0–100, lower is safer) — *"Is this change safe to release?"*

The platform drives a complete governance lifecycle: **DETECT → EXPLAIN → RECOMMEND → REMEDIATE → VALIDATE → RE-SCORE → APPROVE/BLOCK**.

---

## Repository Structure

```
forgeguard/
├── backend/                  # Python FastAPI modular monolith
│   ├── src/forgeguard/       # Main package (src-layout)
│   │   ├── core/             # Configuration, dependency injection
│   │   ├── api/              # FastAPI routers and request/response schemas
│   │   │   └── routes/       # Route handlers grouped by resource
│   │   ├── services/         # Domain logic modules
│   │   ├── data/             # SQLAlchemy models and repositories
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   └── middleware/       # ASGI middleware components
│   ├── alembic/              # Database migration scripts
│   ├── tests/                # Pytest test suite
│   ├── pyproject.toml        # Package manifest and tool configuration
│   ├── ruff.toml             # Ruff linter/formatter configuration
│   ├── .importlinter         # Module boundary enforcement contracts
│   └── Dockerfile            # Multi-stage production Docker image
└── README.md
```

---

## Backend Quickstart

### Prerequisites

- Python 3.12+
- PostgreSQL 16 (or Docker)

### Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configure environment

```bash
cp .env.example .env               # edit as needed
# Minimum required for local dev (defaults work out of the box):
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_dev
# JWT_SECRET_KEY=change-me-locally
```

### Start the development server

```bash
uvicorn forgeguard.main:create_app --factory --reload
# → http://localhost:8000
# → http://localhost:8000/api/v1/docs
```

### Run the test suite

```bash
pytest tests/ -v
```

### Lint and format

```bash
ruff check src/
ruff format --check src/
```

### Check module boundaries

```bash
import-linter --config .importlinter
```

### Run database migrations

```bash
alembic upgrade head
alembic current
```

---

## Architecture

ForgeGuard uses a **layered modular monolith** with strict one-directional dependency rules:

```
API Layer  →  Service Layer  →  Data Layer
```

- The **API layer** (`forgeguard.api`) handles HTTP routing and request/response serialisation. It may call the Service layer but never the Data layer directly.
- The **Service layer** (`forgeguard.services`) contains all domain logic. It may call the Data layer but never the API layer.
- The **Data layer** (`forgeguard.data`) owns database access. It has no upward dependencies.

Module boundary violations are caught at CI time by `import-linter`.

---

## License

Proprietary — see LICENSE.
