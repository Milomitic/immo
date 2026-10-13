from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.listing import _now, _uuid


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

    # Live progress fields — written by a background ticker inside
    # run_spider, polled by the frontend toast to render an ETA bar.
    # ``last_progress_at`` doubles as a heartbeat: if it goes stale the
    # UI can flag the run as frozen / orphaned without touching status.
    progress_done: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str | None] = mapped_column(Text)  # search | fetch | done | failed
    last_progress_at: Mapped[str | None] = mapped_column(Text)
    # All per-portal runs spawned by one ``run_all_spiders`` invocation
    # share a job_id. The status endpoint groups by the most-recent
    # job_id so distinct jobs never bleed into one aggregate.
    job_id: Mapped[str | None] = mapped_column(Text)


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
