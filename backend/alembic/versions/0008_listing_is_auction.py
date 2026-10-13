"""listings.is_auction

Auctions (judicial / online sales) behave nothing like normal listings:
starting price instead of asking price, fixed dates, deposits. The flag is
backfilled from title and description; new scrapes also use immobiliare's
structured ``contract == "auction"``.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 10:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scraper.utils.html_extract import detect_auction

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, not batch mode: rebuilding ``listings`` would drop the
    # full-text triggers from migration 0005 along with the old table.
    op.add_column(
        "listings", sa.Column("is_auction", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, title, description FROM listings")).all()
    auction_ids = [listing_id for listing_id, title, description in rows if detect_auction(title, description)]
    for listing_id in auction_ids:
        conn.execute(sa.text("UPDATE listings SET is_auction = 1 WHERE id = :id"), {"id": listing_id})


def downgrade() -> None:
    op.drop_column("listings", "is_auction")  # SQLite >= 3.35 drops in place
