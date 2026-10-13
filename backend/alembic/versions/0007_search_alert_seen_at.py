"""search alerts: seen_at watermark

Saved searches count what's new since the user last looked at them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-13 20:40:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("search_alerts") as batch:
        batch.add_column(sa.Column("seen_at", sa.Text(), nullable=True))
    op.execute("UPDATE search_alerts SET seen_at = created_at WHERE seen_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("search_alerts") as batch:
        batch.drop_column("seen_at")
