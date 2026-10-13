from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text
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
    # Every listing observed on the portal's search pages this run (new +
    # already-known). ``listings_found`` only counts the ones that went
    # through a detail fetch, so it says nothing about coverage.
    listings_seen: Mapped[int | None] = mapped_column(Integer)
    # True when the spider walked every result page the site offers. Stale
    # listings are only deactivated for portals with full coverage —
    # otherwise anything past the page cap would look "gone".
    coverage_complete: Mapped[bool | None] = mapped_column(Boolean)


class ScrapeError(Base):
    """One row per failure during a run, queryable by portal/kind/time
    (the old ``error_details`` JSON blob on ScrapeRun wasn't)."""

    __tablename__ = "scrape_errors"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(Text, ForeignKey("scrape_runs.id"), nullable=False)
    portal: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # http | network | parse | blocked | spider
    url: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)

    __table_args__ = (
        Index("idx_scrape_errors_run", "run_id"),
        Index("idx_scrape_errors_portal_time", "portal", "created_at"),
    )

