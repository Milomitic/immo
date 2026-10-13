"""Rebuild immobiliare titles that don't describe their listing

The immobiliare spider used to title listings with the agency's free
"caption" ahead of the portal's own title, and some agencies put
boilerplate there: a recruiting line with an e-mail address on every ad
("Lavora in A.P.I. Srl - Curriculum studio@…"), or one slogan on all of
them ("Acquisto Assistito in Asta e Pre-Asta"). The spider now prefers the
portal's title; this rebuilds the stored ones in the same shape
("Trilocale via Roma 9, Murat, Bari") from data already in the row — the
listing itself isn't fetched again.

A title is boilerplate when it carries contact details, or when the same
text titles listings at three or more different addresses: it then
describes none of them. Other portals' titles are left alone.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-14 15:00:00

"""
import re
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTACT = re.compile(r"@|https?://|www\.", re.IGNORECASE)
_SHARED_BY = 3  # distinct addresses

_BY_ROOMS = {1: "Monolocale", 2: "Bilocale", 3: "Trilocale", 4: "Quadrilocale", 5: "Pentalocale"}
_BY_TYPE = {
    "studio": "Monolocale",
    "villa": "Villa",
    "house": "Casa indipendente",
    "loft": "Loft",
    "land": "Terreno",
    "commercial": "Locale commerciale",
}


def rebuild_title(property_type: str | None, rooms: int | None, address: str | None,
                  zone: str | None, city: str | None) -> str:
    """Immobiliare's own title shape: typology, street, zone, city."""
    head = _BY_TYPE.get(property_type or "") or _BY_ROOMS.get(rooms or 0, "Appartamento")
    # "Via don carlo gnocchi, , 9" → "Via don carlo gnocchi 9"
    street = " ".join(p.strip() for p in (address or "").split(",") if p.strip())
    if street:
        head = f"{head} {street}"
    return ", ".join([head, *(p for p in (zone, (city or "").title()) if p)])


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, title, address, zone, city, rooms, property_type FROM listings"
        " WHERE source_portal = 'immobiliare'"
    )).all()

    addresses: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        addresses[row.title].add((row.address or "").strip().lower())

    for row in rows:
        if _CONTACT.search(row.title or "") or len(addresses[row.title]) >= _SHARED_BY:
            # Plain UPDATEs: the full-text triggers (migration 0005) keep the
            # search index in step.
            conn.execute(
                sa.text("UPDATE listings SET title = :title WHERE id = :id"),
                {"title": rebuild_title(row.property_type, row.rooms, row.address, row.zone, row.city),
                 "id": row.id},
            )


def downgrade() -> None:
    pass  # the boilerplate isn't worth restoring
