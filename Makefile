.PHONY: up down build logs backend frontend scrape test test-cov lint format db-migrate db-revision

# Docker (production-like stack: see docker-compose.yml)
up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

# Development: run each in its own terminal
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# Scraping (default city from SCRAPE_DEFAULT_CITY, i.e. Bari)
scrape:
	cd backend && python -m scraper.runner

scrape-%:
	cd backend && python -m scraper.runner --portal $*

# Testing
test:
	cd backend && pytest -v

test-cov:
	cd backend && pytest --cov=app --cov=scraper --cov-report=html

# Linting
lint:
	cd backend && ruff check .
	cd frontend && npm run lint && npm run typecheck

format:
	cd backend && ruff format .

# Database (migrations also run automatically at startup)
db-migrate:
	cd backend && alembic upgrade head

db-revision:
	cd backend && alembic revision --autogenerate -m "$(msg)"
