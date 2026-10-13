from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.scrape_run import ScrapeRun
from app.services import scheduler
from app.services.scheduler import scheduler_tick

NOW = datetime.now(timezone.utc)


@pytest.fixture
def launches(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(scheduler, "launch_scrape", lambda city, portal=None: calls.append(city))
    monkeypatch.setattr(settings, "SCRAPE_INTERVAL_HOURS", 6)
    return calls


async def _run(db_session, hours_ago: float, status: str = "completed"):
    started = NOW - timedelta(hours=hours_ago)
    db_session.add(ScrapeRun(
        portal="casa", status=status, started_at=started.isoformat(),
        # A running row needs a fresh heartbeat, or the reaper closes it.
        last_progress_at=NOW.isoformat() if status == "running" else started.isoformat(),
    ))
    await db_session.commit()


async def test_never_scraped_is_due(launches):
    assert await scheduler_tick(NOW) is True
    assert launches == [settings.SCRAPE_DEFAULT_CITY]


async def test_recent_scan_is_not_due(launches, db_session):
    await _run(db_session, hours_ago=2)
    assert await scheduler_tick(NOW) is False
    assert launches == []


async def test_scan_older_than_the_interval_is_due(launches, db_session):
    await _run(db_session, hours_ago=7)
    assert await scheduler_tick(NOW) is True


async def test_never_overlaps_a_running_scan(launches, db_session):
    await _run(db_session, hours_ago=8, status="running")
    assert await scheduler_tick(NOW) is False
    assert launches == []
