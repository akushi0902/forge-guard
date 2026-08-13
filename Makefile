# ForgeGuard — Developer convenience targets
#
# Requirements:
#   - Docker Compose v2.20+ (check: docker compose version)
#   - openssl (for cert generation)
#
# Quick start:
#   make setup   # one-time setup: generate certs + copy .env
#   make up      # build and start all services
#   open https://localhost

.PHONY: help setup certs env up dev down logs clean ps shell-backend shell-db test test-ci test-backend lint-backend

# Default target — print help.
help:
	@echo ""
	@echo "ForgeGuard — Makefile targets"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  make setup          One-time developer setup (certs + .env)"
	@echo "  make up             Build images and start all services"
	@echo "  make dev            Start with hot-reload dev overrides"
	@echo "  make down           Stop all services"
	@echo "  make logs           Tail all service logs (Ctrl-C to stop)"
	@echo "  make clean          Stop, remove volumes, remove local images"
	@echo "  make ps             Show service status"
	@echo "  make shell-backend  Open a shell in the backend container"
	@echo "  make shell-db       Open psql in the database container"
	@echo "  make test           Run backend pytest suite locally (requires Docker for DB)"
	@echo "  make test-ci        Run backend pytest with JUnit XML output for CI"
	@echo "  make test-backend   Run backend pytest suite inside Docker container"
	@echo "  make lint-backend   Run ruff check + format check on backend"
	@echo "  make certs          (Re)generate self-signed TLS certificates"
	@echo "  make env            Copy .env.example → .env (if .env absent)"
	@echo ""

# ─── One-time setup ────────────────────────────────────────────────────── #

setup: certs env
	@echo ""
	@echo "✓ Setup complete. Run 'make up' to start the stack."

certs:
	@bash scripts/generate-dev-certs.sh

env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ Created .env from .env.example — review and update the values."; \
	else \
		echo "  .env already exists — skipping copy."; \
	fi

# ─── Docker Compose targets ────────────────────────────────────────────── #

up:
	docker compose up --build -d
	@echo ""
	@echo "✓ Stack started. Services:"
	@docker compose ps
	@echo ""
	@echo "  Frontend:  https://localhost/"
	@echo "  API docs:  https://localhost/api/v1/docs"
	@echo "  API health: https://localhost/api/v1/health"

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local
	@echo "✓ All containers, volumes, and locally-built images removed."

ps:
	docker compose ps

# ─── Developer shells ──────────────────────────────────────────────────── #

shell-backend:
	docker compose exec forgeguard-backend /bin/bash

shell-db:
	docker compose exec forgeguard-db psql -U $${POSTGRES_USER:-forgeguard} -d $${POSTGRES_DB:-forgeguard_dev}

# ─── Testing / linting (run inside container or local venv) ─────────────── #

test:
	cd backend && pytest -v --cov --cov-report=term-missing --cov-report=html

test-ci:
	cd backend && pytest -v --cov --cov-report=term-missing --cov-report=xml --junitxml=results.xml

test-backend:
	docker compose exec forgeguard-backend pytest /app/../tests/ -v

lint-backend:
	docker compose exec forgeguard-backend sh -c "cd /app && ruff check src/ && ruff format --check src/"
