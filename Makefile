.PHONY: dev up down build logs scrape test lint

# Docker commands
up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

# Development
dev:
	docker-compose up

# Backend only
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# Frontend only
frontend:
	cd frontend && npm run dev

# Scraping
scrape:
	cd backend && python -m scraper.runner

scrape-immobiliare:
	cd backend && python -m scraper.runner --portal immobiliare

scrape-idealista:
	cd backend && python -m scraper.runner --portal idealista

scrape-casa:
	cd backend && python -m scraper.runner --portal casa

# Testing
test:
	cd backend && pytest -v

test-cov:
	cd backend && pytest --cov=app --cov=scraper --cov-report=html

# Linting
lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

# Database
db-migrate:
	cd backend && alembic upgrade head

db-revision:
	cd backend && alembic revision --autogenerate -m "$(msg)"
