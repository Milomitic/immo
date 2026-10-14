"""Repair double-encoded UTF-8 in stored titles and descriptions

Some TrovaCasa text is double-encoded ("Ã¨" for "è", "â€“" for "–"). The
spider now repairs it as it reads; listings stored before the repair
handled mixed text keep their snapshot, so they're fixed here. Only the
unmistakable sequences change (scraper.utils.html_extract.fix_mojibake).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-14 13:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from scraper.utils.html_extract import fix_mojibake

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, title, description FROM listings"
        " WHERE title LIKE '%Ã%' OR title LIKE '%Â%' OR title LIKE '%â%'"
        " OR description LIKE '%Ã%' OR description LIKE '%Â%' OR description LIKE '%â%'"
    )).all()
    for listing_id, title, description in rows:
        fixed_title, fixed_description = fix_mojibake(title), fix_mojibake(description) or None
        if (fixed_title, fixed_description) != (title, description):
            # Plain UPDATE: the full-text triggers keep the search index in step.
            conn.execute(
                sa.text("UPDATE listings SET title = :t, description = :d WHERE id = :id"),
                {"t": fixed_title, "d": fixed_description, "id": listing_id},
            )


def downgrade() -> None:
    pass  # the broken text isn't worth restoring
