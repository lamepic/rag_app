# Developer commands. Run `make` or `make help` to list them.
.DEFAULT_GOAL := help
.PHONY: help install up down migrate dev run check fmt test cov

APP := rag.main:create_app
PORT ?= 8000

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies from uv.lock
	uv sync

up: ## Start Supabase and Redis (no-op if already running)
	@supabase status > /dev/null 2>&1 || supabase start
	docker compose up -d --wait

down: ## Stop Supabase and Redis (data is kept)
	docker compose down
	supabase stop

migrate: ## Apply database migrations
	uv run alembic upgrade head

dev: up migrate run ## Start everything, migrate, then run the API with auto-reload

run: ## Run the API with auto-reload (services must already be up)
	uv run uvicorn $(APP) --factory --reload --port $(PORT)

check: ## Lint, format check, type check and test: what CI runs
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run pytest

fmt: ## Auto-fix lint issues and reformat code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run tests
	uv run pytest

cov: ## Run tests with a coverage report
	uv run pytest --cov --cov-report=term-missing
