SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help bootstrap lock up down migrate seed format format-check lint typecheck test test-integration test-e2e contract-check migration-check compose-validate verify security clean-local

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Available targets:\n"} /^[a-zA-Z_-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install locked Python and web dependencies
	uv sync --all-packages --all-groups
	corepack enable
	pnpm install --frozen-lockfile

lock: ## Refresh dependency lockfiles intentionally
	uv lock
	pnpm install --lockfile-only

up: ## Start the complete local stack
	docker compose up --build -d

down: ## Stop the local stack while preserving data
	docker compose down

migrate: ## Apply all service-owned migrations
	docker compose run --rm control-plane alembic upgrade head
	docker compose run --rm integrations alembic upgrade head
	docker compose run --rm delivery alembic upgrade head

seed: ## Seed deterministic local data
	docker compose run --rm control-plane python -m mvp_control_plane.seed
	docker compose run --rm integrations python -m mvp_integrations.seed
	docker compose run --rm delivery python -m mvp_delivery.seed

format: ## Format source files
	uv run ruff format packages services runners
	pnpm --recursive format

format-check: ## Check formatting without rewriting
	uv run ruff format --check packages services runners
	pnpm --recursive format:check

lint: ## Run Python and TypeScript linters
	uv run ruff check packages services runners
	pnpm --recursive lint

typecheck: ## Run strict Python and TypeScript type checking
	uv run mypy packages/python_common/src packages/python_observability/src services/*/src runners/*/src
	pnpm --recursive typecheck

test: ## Run deterministic unit tests
	uv run pytest -m "not integration"
	pnpm --recursive test

test-integration: ## Run infrastructure-backed integration tests
	uv run pytest -m integration

test-e2e: ## Run the browser vertical slice against the local Compose stack
	pnpm --filter @mvp-master/web test:e2e

contract-check: ## Validate versioned contract files
	uv run python scripts/check_contracts.py
	uv run python scripts/export_openapi.py --check

migration-check: ## Compile every Alembic history to PostgreSQL SQL
	cd services/control_plane && uv run alembic upgrade head --sql >/dev/null
	cd services/integrations && uv run alembic upgrade head --sql >/dev/null
	cd services/delivery && uv run alembic upgrade head --sql >/dev/null

compose-validate: ## Validate the Compose model
	docker compose config --quiet

security: ## Run repository dependency checks available locally
	uv run pip-audit
	pnpm audit --audit-level high

verify: format-check lint typecheck test contract-check migration-check compose-validate ## Run required deterministic quality gates

clean-local: ## Remove only this Compose project's containers and volumes
	@read -r -p "Remove local MVP Master containers and volumes? [y/N] " answer; \
	if [[ "$$answer" == "y" ]]; then docker compose down --volumes --remove-orphans; fi
