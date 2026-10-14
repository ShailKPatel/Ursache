# Local development. Requires Docker, uv and pnpm on the host.
SHELL := /bin/bash
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help up down migrate roles seed bootstrap api web install lint format typecheck test test-integration

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-17s %s\n", $$1, $$2}'

up: ## Start Postgres and Qdrant
	docker compose up -d --wait

down: ## Stop services (data volumes are kept)
	docker compose down

install: ## Install backend and frontend dependencies
	$(BACKEND) uv sync --frozen
	$(FRONTEND) pnpm install --frozen-lockfile

migrate: ## Apply database migrations
	$(BACKEND) uv run ursache db-migrate

roles: ## Create/refresh schemas, roles and grants
	$(BACKEND) uv run ursache db-roles

seed: ## Insert seed users
	$(BACKEND) uv run ursache db-seed

bootstrap: ## Create Qdrant collections and aliases
	$(BACKEND) uv run ursache qdrant-bootstrap

api: ## Run the API with reload on :8000
	$(BACKEND) uv run uvicorn ursache.api.main:create_app --factory --reload --port 8000

web: ## Run the Next.js dev server on :3000
	$(FRONTEND) pnpm dev

lint: ## Lint backend and frontend
	$(BACKEND) uv run ruff check . && uv run ruff format --check .
	$(FRONTEND) pnpm lint && pnpm format:check

format: ## Auto-format backend and frontend
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
	$(FRONTEND) pnpm format

typecheck: ## Type-check backend (pyright) and frontend (tsc)
	$(BACKEND) uv run pyright
	$(FRONTEND) pnpm typecheck

test: ## Unit tests (no services needed)
	$(BACKEND) uv run pytest tests/unit
	$(FRONTEND) pnpm test

test-integration: ## Integration tests (needs `make up`)
	$(BACKEND) uv run pytest tests/integration
