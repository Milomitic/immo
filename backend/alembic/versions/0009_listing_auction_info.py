"""listings.auction_info

The sale's data of judicial auctions — date, base price, minimum offer,
court, procedure, Portale Vendite Pubbliche link, notice documents — as
JSON. Filled by portals that publish it (Wikicasa); empty for older rows.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, not batch mode: rebuilding ``listings`` would drop the
    # full-text triggers from migration 0005 along with the old table.
    op.add_column("listings", sa.Column("auction_info", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "auction_info")  # SQLite >= 3.35 drops in place
