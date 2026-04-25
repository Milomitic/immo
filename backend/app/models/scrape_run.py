from app.database import Base
from app.models.listing import _now, _uuid

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    portal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    listings_found: Mapped[int] = mapped_column(Integer, default=0)
    listings_new: Mapped[int] = mapped_column(Integer, default=0)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0)
    listings_deactivated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    error_details: Mapped[str | None] = mapped_column(Text)  # JSON array
    config: Mapped[str | None] = mapped_column(Text)  # JSON


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    listing_id: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)


class SearchAlert(Base):
    __tablename__ = "search_alerts"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[str | None] = mapped_column(Text)  # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notified_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)
