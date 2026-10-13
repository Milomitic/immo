"""recompute feature flags from description

casa.it and remax derived has_elevator/has_garden/… by searching the whole
page text, where sidebar facets and SEO links mention every feature: 82% of
casa.it listings came out with an elevator while 6% mentioned one. Those
values carry no information, so for those portals' canonical listings we
recompute the flags from the stored description (True / False when
negated / NULL when unknown). New scrapes use structured data.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 18:20:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scraper.utils.html_extract import detect_feature

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLAGS = {
    "has_elevator": ("ascensore",),
    "has_balcony": ("balcon",),
    "has_terrace": ("terrazz",),
    "has_garage": ("garage", "box auto", "posto auto"),
    "has_garden": ("giardin",),
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, description FROM listings WHERE source_portal IN ('casa', 'remax')")
    ).all()
    update = sa.text(
        "UPDATE listings SET "
        + ", ".join(f"{col} = :{col}" for col in _FLAGS)
        + " WHERE id = :id"
    )
    for listing_id, description in rows:
        params = {col: detect_feature(description, *kw) for col, kw in _FLAGS.items()}
        conn.execute(update, {"id": listing_id, **params})


def downgrade() -> None:
    # The original values were noise; there is nothing meaningful to restore.
    pass
