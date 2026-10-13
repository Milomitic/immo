"""Launching scrapes and answering "is one already running?".

Shared by the trigger endpoint and the periodic scheduler so both apply
the same rules: only enabled portals, never two jobs at once.
"""

import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.scrape_run import ScrapeRun

ALL_PORTALS = (
    "immobiliare", "casa", "tecnocasa", "remax", "gabetti", "vistocasa", "wikicasa", "subito",
    "idealista",
)

# A "running" row whose heartbeat is older than this belongs to a dead
# worker (killed process, crash) and must not block new scrapes.
STALE_AFTER = timedelta(seconds=120)

# The subprocess needs a second or two to import and insert its first
# ScrapeRun row; a trigger landing in that window would pass the DB check.
_LAUNCH_GRACE_SECONDS = 30
_last_launch_monotonic: float | None = None

_BACKEND_DIR = Path(__file__).resolve().parents[2]


# The runner's heartbeat ticks every 2s even while a request hangs, so this
# much silence means the process is gone (killed, crashed, machine slept).
ORPHAN_AFTER = timedelta(minutes=10)


async def reap_orphaned_runs(db: AsyncSession) -> int:
    """Close out ``running`` rows whose worker died, so they stop blocking
    the UI ("scan in progress" forever) and the status aggregate."""
    now = datetime.now(timezone.utc)
    cutoff = (now - ORPHAN_AFTER).isoformat()
    result = await db.execute(
        update(ScrapeRun)
        .where(
            ScrapeRun.status == "running",
            or_(ScrapeRun.last_progress_at.is_(None), ScrapeRun.last_progress_at < cutoff),
            ScrapeRun.started_at < cutoff,
        )
        .values(
            status="failed",
            phase="failed",
            finished_at=now.isoformat(),
            error_details='["worker stopped responding (no heartbeat)"]',
        )
    )
    await db.commit()
    return result.rowcount or 0


def enabled_portals() -> list[str]:
    """Portals whose ``SCRAPE_<PORTAL>_ENABLED`` flag is true."""
    return [p for p in ALL_PORTALS if getattr(settings, f"SCRAPE_{p.upper()}_ENABLED", False)]


async def scrape_in_progress(db: AsyncSession) -> bool:
    global _last_launch_monotonic
    if _last_launch_monotonic is not None and time.monotonic() - _last_launch_monotonic < _LAUNCH_GRACE_SECONDS:
        return True
    cutoff = (datetime.now(timezone.utc) - STALE_AFTER).isoformat()
    row = (
        await db.execute(
            select(ScrapeRun.id).where(
                ScrapeRun.status == "running",
                ScrapeRun.last_progress_at >= cutoff,
            ).limit(1)
        )
    ).first()
    return row is not None


def launch_scrape(city: str, portal: str | None = None) -> None:
    """Start ``python -m scraper.runner`` as a process detached from the API.

    Not a FastAPI BackgroundTask: that lives inside uvicorn and dies on
    every reload or deploy. The detached process keeps running and reports
    progress through the shared DB (heartbeat ticker in the runner).
    """
    global _last_launch_monotonic
    args = [sys.executable, "-m", "scraper.runner", "--city", city]
    if portal:
        args += ["--portal", portal]

    kwargs: dict = {}
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        # Own session: survives the parent and its SIGHUP/SIGINT.
        kwargs["start_new_session"] = True

    subprocess.Popen(
        args,
        cwd=str(_BACKEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        **kwargs,
    )
    _last_launch_monotonic = time.monotonic()
