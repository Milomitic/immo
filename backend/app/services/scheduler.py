"""Periodic scans, opt-in via SCRAPE_SCHEDULE_ENABLED.

A loop in the API process checks every few minutes whether a scan is due:
the newest scrape run (manual or scheduled) is older than
SCRAPE_INTERVAL_HOURS and nothing is running. Due-ness comes from the
database, not from in-memory timers, so restarts (uvicorn --reload) neither
skip a scan nor fire an extra one.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models.scrape_run import ScrapeRun
from app.services.scrape_service import launch_scrape, reap_orphaned_runs, scrape_in_progress

logger = structlog.get_logger()

CHECK_EVERY_SECONDS = 300


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def scheduler_tick(now: datetime | None = None) -> bool:
    """Launch a scan when one is due. Returns True if it launched one."""
    now = now or datetime.now(timezone.utc)
    async with async_session() as db:
        await reap_orphaned_runs(db)
        if await scrape_in_progress(db):
            return False
        last = _parse((await db.execute(select(func.max(ScrapeRun.started_at)))).scalar())
    if last is not None and now - last < timedelta(hours=settings.SCRAPE_INTERVAL_HOURS):
        return False
    launch_scrape(settings.SCRAPE_DEFAULT_CITY)
    logger.info("scheduled_scrape_launched", city=settings.SCRAPE_DEFAULT_CITY, last_run=last)
    return True


async def run_scheduler(stop: asyncio.Event) -> None:
    logger.info("scheduler_started", every_hours=settings.SCRAPE_INTERVAL_HOURS)
    while not stop.is_set():
        try:
            await scheduler_tick()
        except Exception:  # keep the loop alive; the next tick retries
            logger.exception("scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=CHECK_EVERY_SECONDS)
        except asyncio.TimeoutError:
            pass
