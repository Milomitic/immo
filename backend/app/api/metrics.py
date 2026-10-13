"""Prometheus metrics at ``/metrics``.

Scrapes run in a separate process (see app.services.scrape_service), so
in-memory counters here would never see them: the catalogue and scrape
figures are read from the shared DB at each Prometheus scrape. Request
latency is measured in-process by app.observability.MetricsMiddleware.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import settings
from app.models.listing import Listing
from app.models.scrape_run import ScrapeError, ScrapeRun
from app.observability import REGISTRY

router = APIRouter(tags=["metrics"])

_FINISHED_OK = ("completed", "completed_with_errors")


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


class _Families:
    """Adapter: lets ``generate_latest`` render a list of metric families."""

    def __init__(self, families):
        self._families = families

    def collect(self):
        return self._families


async def _listing_families(db: AsyncSession) -> list:
    listings = GaugeMetricFamily(
        "immo_listings", "Listings in the catalogue, by portal and state.", labels=["portal", "state"]
    )
    rows = await db.execute(
        select(Listing.source_portal, Listing.is_active, func.count()).group_by(
            Listing.source_portal, Listing.is_active
        )
    )
    for portal, active, count in rows:
        listings.add_metric([portal, "active" if active else "inactive"], count)
    return [listings]


async def _scrape_families(db: AsyncSession) -> list:
    running = GaugeMetricFamily("immo_scrape_running", "Portal scrapes currently running.")
    running.add_metric(
        [], (await db.execute(select(func.count()).where(ScrapeRun.status == "running"))).scalar_one()
    )

    last_success = GaugeMetricFamily(
        "immo_scrape_last_success_timestamp_seconds",
        "When each portal last finished a scrape (with or without errors). Alert on its age.",
        labels=["portal"],
    )
    for portal, finished in await db.execute(
        select(ScrapeRun.portal, func.max(ScrapeRun.finished_at))
        .where(ScrapeRun.status.in_(_FINISHED_OK), ScrapeRun.finished_at.isnot(None))
        .group_by(ScrapeRun.portal)
    ):
        ts = _epoch(finished)
        if ts is not None:
            last_success.add_metric([portal], ts)

    # The latest finished run of each portal, whatever its outcome.
    latest = (
        select(ScrapeRun.portal, func.max(ScrapeRun.finished_at).label("finished_at"))
        .where(ScrapeRun.finished_at.isnot(None))
        .group_by(ScrapeRun.portal)
        .subquery()
    )
    runs = (
        await db.execute(
            select(ScrapeRun).join(
                latest,
                and_(ScrapeRun.portal == latest.c.portal, ScrapeRun.finished_at == latest.c.finished_at),
            )
        )
    ).scalars().all()

    duration = GaugeMetricFamily(
        "immo_scrape_last_duration_seconds", "Duration of each portal's latest scrape.", labels=["portal"]
    )
    outcome = GaugeMetricFamily(
        "immo_scrape_last_status",
        "Outcome of each portal's latest scrape: 1 for its status, 0 for the others.",
        labels=["portal", "status"],
    )
    coverage = GaugeMetricFamily(
        "immo_scrape_last_coverage_complete",
        "1 if the latest scrape saw the portal's whole catalogue (the precondition for deactivating vanished listings).",
        labels=["portal"],
    )
    counts = GaugeMetricFamily(
        "immo_scrape_last_listings",
        "Listings handled by each portal's latest scrape.",
        labels=["portal", "kind"],
    )
    reported: set[str] = set()
    for run in runs:
        # Two runs finishing in the same instant would yield duplicate
        # series, which makes the whole exposition invalid.
        if run.portal in reported:
            continue
        reported.add(run.portal)
        start, end = _epoch(run.started_at), _epoch(run.finished_at)
        if start is not None and end is not None:
            duration.add_metric([run.portal], max(0.0, end - start))
        for status in ("completed", "completed_with_errors", "failed"):
            outcome.add_metric([run.portal, status], 1 if run.status == status else 0)
        if run.coverage_complete is not None:
            coverage.add_metric([run.portal], 1 if run.coverage_complete else 0)
        for kind, value in (
            ("seen", run.listings_seen),
            ("new", run.listings_new),
            ("updated", run.listings_updated),
            ("deactivated", run.listings_deactivated),
        ):
            if value is not None:  # older runs didn't record "seen"
                counts.add_metric([run.portal, kind], value)

    # scrape_errors rows are never pruned, so the count only grows: a counter.
    errors = CounterMetricFamily(
        "immo_scrape_errors", "Scrape errors recorded, by portal and kind.", labels=["portal", "kind"]
    )
    for portal, kind, count in await db.execute(
        select(ScrapeError.portal, ScrapeError.kind, func.count()).group_by(
            ScrapeError.portal, ScrapeError.kind
        )
    ):
        errors.add_metric([portal, kind], count)

    return [running, last_success, duration, outcome, coverage, counts, errors]


@router.get("/metrics", include_in_schema=False)
async def metrics(db: AsyncSession = Depends(get_db)) -> Response:
    if not settings.METRICS_ENABLED:
        raise HTTPException(status_code=404)
    families = await _listing_families(db) + await _scrape_families(db)
    body = generate_latest(REGISTRY) + generate_latest(_Families(families))
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
