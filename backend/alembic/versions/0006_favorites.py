"""favorites: one per listing, removed with it

The baseline created ``favorites`` without constraints (the feature was
never wired up). Saving now relies on one row per listing and on the row
going away with its listing, so orphans and duplicates are dropped and the
table is rebuilt with a unique constraint and an ON DELETE CASCADE key.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13 20:05:00

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM favorites WHERE listing_id NOT IN (SELECT id FROM listings)")
    op.execute(
        "DELETE FROM favorites WHERE rowid NOT IN "
        "(SELECT min(rowid) FROM favorites GROUP BY listing_id)"
    )
    with op.batch_alter_table("favorites", recreate="always") as batch:
        batch.create_unique_constraint("uq_favorites_listing_id", ["listing_id"])
        batch.create_foreign_key(
            "fk_favorites_listing_id_listings", "listings",
            ["listing_id"], ["id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("favorites", recreate="always") as batch:
        batch.drop_constraint("fk_favorites_listing_id_listings", type_="foreignkey")
        batch.drop_constraint("uq_favorites_listing_id", type_="unique")
