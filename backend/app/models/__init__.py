"""Importing the package registers every table on ``Base.metadata`` —
Alembic and the test fixtures rely on that, so new model modules belong here."""

from app.models import favorite, listing, scrape_run  # noqa: F401
