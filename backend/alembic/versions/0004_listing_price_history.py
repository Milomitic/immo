"""listing price history

Append-only price series per listing, for charts. Backfilled from what the
listings table already knows: the first observed price (``price_previous``
when a change was recorded, else the current price) at ``first_seen_at``,
then the current price at ``price_changed_at``.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13 19:10:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("source_portal", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_price_history_listing", "listing_price_history", ["listing_id", "observed_at"]
    )

    op.execute(
        """
        INSERT INTO listing_price_history (listing_id, price, source_portal, observed_at)
        SELECT id, price_previous, source_portal, first_seen_at
        FROM listings WHERE price_previous IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO listing_price_history (listing_id, price, source_portal, observed_at)
        SELECT id, price, source_portal,
               CASE WHEN price_previous IS NOT NULL
                    THEN COALESCE(price_changed_at, first_seen_at)
                    ELSE first_seen_at END
        FROM listings WHERE price IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("idx_price_history_listing", table_name="listing_price_history")
    op.drop_table("listing_price_history")
