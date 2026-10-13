FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl for the compose healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, in their own layer: rebuilt only when pyproject.toml
# changes. The stub packages let pip resolve the project; the code itself
# runs from /app (uvicorn and `python -m` put the working dir on sys.path).
COPY pyproject.toml .
RUN mkdir -p app scraper && touch app/__init__.py scraper/__init__.py \
    && pip install . \
    && pip uninstall -y immo-backend \
    && rm -rf app scraper build *.egg-info

COPY . .

EXPOSE 8000

# Migrations run at startup (app.database.init_db), with a backup first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
