# ForgeGuard Backend — Multi-stage Docker build
#
# Stage 1 (builder): Installs Python dependencies into an isolated prefix so
#                    that only the installed packages are copied to the runtime
#                    image — keeping it lean.
# Stage 2 (runtime): Minimal runtime image with no build tools.
#
# Build:
#   docker build -t forgeguard-backend:latest .
#
# Run (development):
#   docker run -p 8000:8000 --env-file ../.env forgeguard-backend:latest
#
# Run (production — gunicorn with uvicorn workers):
#   docker run -p 8000:8000 \
#     -e DATABASE_URL=... \
#     -e JWT_SECRET_KEY=... \
#     -e APP_ENV=production \
#     forgeguard-backend:latest

# ============================================================ #
# Stage 1: builder
# ============================================================ #
FROM python:3.12-slim AS builder

# Install build-time system dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy the package manifest first — Docker layer caching avoids reinstalling
# deps when only application source code has changed.
COPY pyproject.toml ./
COPY src/ ./src/

# Install runtime dependencies into a custom prefix.
# We explicitly avoid installing dev extras in the production image.
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install .

# ============================================================ #
# Stage 2: runtime
# ============================================================ #
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ForgeGuard Backend"
LABEL org.opencontainers.image.description="AI-powered Engineering Governance and Release Readiness platform"
LABEL org.opencontainers.image.source="https://github.com/your-org/forgeguard"

# Install only the minimal runtime system libraries (asyncpg needs libpq).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security hardening.
RUN groupadd --gid 1001 forgeguard \
    && useradd --uid 1001 --gid forgeguard --no-create-home --shell /sbin/nologin forgeguard

# Copy the installed packages from the builder stage.
COPY --from=builder /install /usr/local

# Copy application source.
COPY --chown=forgeguard:forgeguard src/ /app/src/

# Copy Alembic migration files so the migration container can run
# 'alembic upgrade head' using this same image.
COPY --chown=forgeguard:forgeguard alembic/ /app/alembic/
COPY --chown=forgeguard:forgeguard alembic.ini /app/alembic.ini

WORKDIR /app

# Expose the PYTHONPATH so that the src-layout package is importable.
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

USER forgeguard

EXPOSE 8000

# Production command: gunicorn with uvicorn workers.
# Override with docker run ... --cmd for development or debugging.
CMD ["gunicorn", "forgeguard.main:create_app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
