from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GeocodeCache(Base):
    """Nominatim answers, kept forever: its usage policy asks clients to
    cache, and a street doesn't move. A miss is cached too (result None)."""

    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(Text, primary_key=True)  # lowercased free-form query
    result: Mapped[str | None] = mapped_column(Text)  # JSON {lat, lng, category, type}
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
