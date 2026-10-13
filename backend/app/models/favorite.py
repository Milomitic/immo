import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.listing import Listing


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Favorite(Base):
    """A saved listing. The app is single-user, so this is one shared list
    (kept server-side so it follows the user across browsers)."""

    __tablename__ = "favorites"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    listing_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("listings.id", ondelete="CASCADE", name="fk_favorites_listing_id_listings"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)

    listing: Mapped[Listing] = relationship()

    __table_args__ = (UniqueConstraint("listing_id", name="uq_favorites_listing_id"),)
