"""listings.geo_precision and the geocode cache

Listings without a position get an approximate one (street, zone or town
centre: app.services.geolocate). ``geo_precision`` says which — None is
the portal's own position — so the map can mark the pin as approximate
and deduplication can ignore it. ``geocode_cache`` keeps Nominatim's
answers, as its usage policy asks.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14 17:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, not batch mode: rebuilding ``listings`` would drop the
    # full-text triggers from migration 0005 along with the old table.
    op.add_column("listings", sa.Column("geo_precision", sa.Text(), nullable=True))
    op.create_table(
        "geocode_cache",
        sa.Column("query", sa.Text(), primary_key=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("geocode_cache")
    op.drop_column("listings", "geo_precision")  # SQLite >= 3.35 drops in place
