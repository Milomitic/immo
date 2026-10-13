"""listings full-text index (SQLite FTS5)

External-content FTS5 table over the listings' text columns, kept in sync
by triggers. ``remove_diacritics 2`` makes "citta" match "città".

The index is keyed by the implicit ``listings.rowid`` (the primary key is a
TEXT uuid). SQLite may renumber implicit rowids on VACUUM, so after a VACUUM
run ``INSERT INTO listings_fts(listings_fts) VALUES('rebuild')``.

Other databases skip this migration; search falls back to LIKE there.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 19:15:00

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = "title, description, address, zone, city"
_NEW = ", ".join(f"new.{c.strip()}" for c in _COLUMNS.split(","))
_OLD = ", ".join(f"old.{c.strip()}" for c in _COLUMNS.split(","))


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        f"""
        CREATE VIRTUAL TABLE listings_fts USING fts5(
            {_COLUMNS},
            content='listings', content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER listings_fts_ai AFTER INSERT ON listings BEGIN
            INSERT INTO listings_fts(rowid, {_COLUMNS}) VALUES (new.rowid, {_NEW});
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER listings_fts_ad AFTER DELETE ON listings BEGIN
            INSERT INTO listings_fts(listings_fts, rowid, {_COLUMNS})
            VALUES ('delete', old.rowid, {_OLD});
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER listings_fts_au AFTER UPDATE OF {_COLUMNS} ON listings BEGIN
            INSERT INTO listings_fts(listings_fts, rowid, {_COLUMNS})
            VALUES ('delete', old.rowid, {_OLD});
            INSERT INTO listings_fts(rowid, {_COLUMNS}) VALUES (new.rowid, {_NEW});
        END
        """
    )
    op.execute("INSERT INTO listings_fts(listings_fts) VALUES ('rebuild')")


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    for trigger in ("listings_fts_ai", "listings_fts_ad", "listings_fts_au"):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS listings_fts")
