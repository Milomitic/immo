from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.api.scrape as scrape_api
from app.config import settings
from app.main import app
from app.models.scrape_run import ScrapeError, ScrapeRun


def _ts(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def launches(monkeypatch):
    calls = []
    monkeypatch.setattr(scrape_api, "launch_scrape", lambda city, portal=None: calls.append((city, portal)))
    return calls


async def test_trigger_launches_enabled_portals(client, launches):
    r = await client.post("/api/v1/scrape/trigger", json={"portal": "all"})
    assert r.status_code == 202
    body = r.json()
    assert launches == [("bari", None)]
    assert "idealista" not in body["portals"]  # disabled by default
    assert "immobiliare" in body["portals"]


async def test_trigger_single_portal(client, launches):
    r = await client.post("/api/v1/scrape/trigger", json={"portal": "casa", "city": "Molfetta"})
    assert r.status_code == 202
    assert launches == [("molfetta", "casa")]


async def test_unknown_portal_is_422(client, launches):
    r = await client.post("/api/v1/scrape/trigger", json={"portal": "nope"})
    assert r.status_code == 422
    assert launches == []


async def test_second_trigger_while_running_is_409(client, launches, db_session):
    db_session.add(ScrapeRun(portal="casa", status="running", started_at=_ts(minutes=1),
                             last_progress_at=_ts(seconds=5), job_id="j1"))
    await db_session.commit()
    r = await client.post("/api/v1/scrape/trigger", json={"portal": "all"})
    assert r.status_code == 409
    assert launches == []


async def test_stale_running_row_does_not_block(client, launches, db_session):
    # Heartbeat 5 minutes old: worker hung/dead, must not block a new scan.
    db_session.add(ScrapeRun(portal="casa", status="running", started_at=_ts(minutes=6),
                             last_progress_at=_ts(minutes=5), job_id="j1"))
    await db_session.commit()
    r = await client.post("/api/v1/scrape/trigger", json={"portal": "all"})
    assert r.status_code == 202


async def test_admin_token_enforced_when_set(client, launches, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "s3cret")
    assert (await client.post("/api/v1/scrape/trigger", json={})).status_code == 401
    r = await client.post("/api/v1/scrape/trigger", json={}, headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 202


async def test_orphaned_runs_are_reaped(client, db_session):
    db_session.add(ScrapeRun(portal="casa", status="running", started_at=_ts(hours=2),
                             last_progress_at=_ts(minutes=30), job_id="old"))
    await db_session.commit()
    await client.get("/api/v1/scrape/status")
    db_session.expire_all()
    run = (await db_session.get(ScrapeRun, (await _only_run_id(db_session))))
    assert run.status == "failed"


async def _only_run_id(session) -> str:
    from sqlalchemy import select
    return (await session.execute(select(ScrapeRun.id))).scalar_one()


async def test_status_aggregates_latest_job_only(client, db_session):
    db_session.add_all([
        ScrapeRun(portal="casa", status="completed", started_at=_ts(minutes=50),
                  finished_at=_ts(minutes=40), progress_done=10, progress_total=10, job_id="old"),
        ScrapeRun(portal="casa", status="running", started_at=_ts(minutes=2),
                  last_progress_at=_ts(seconds=3), progress_done=5, progress_total=20,
                  phase="fetch", job_id="new"),
        ScrapeRun(portal="remax", status="running", started_at=_ts(minutes=2),
                  last_progress_at=_ts(seconds=3), progress_done=1, progress_total=4,
                  phase="search", job_id="new"),
    ])
    await db_session.commit()
    body = (await client.get("/api/v1/scrape/status")).json()
    assert body["is_running"] is True
    assert body["is_stale"] is False
    assert body["phase"] == "search"  # least advanced portal
    # Only the runs in that phase: remax's search pages, not casa's details.
    assert (body["progress_done"], body["progress_total"]) == (1, 4)
    assert {r["job_id"] for r in body["runs"]} == {"new"}


async def test_status_flags_hung_worker(client, db_session):
    db_session.add(ScrapeRun(portal="casa", status="running", started_at=_ts(minutes=4),
                             last_progress_at=_ts(minutes=3), job_id="j"))
    await db_session.commit()
    body = (await client.get("/api/v1/scrape/status")).json()
    assert body["is_running"] is True
    assert body["is_stale"] is True


async def test_errors_endpoints(client, db_session):
    run = ScrapeRun(portal="casa", status="completed_with_errors", started_at=_ts(minutes=5), job_id="j")
    db_session.add(run)
    await db_session.flush()
    db_session.add_all([
        ScrapeError(run_id=run.id, portal="casa", kind="blocked", status_code=403, message="HTTP 403"),
        ScrapeError(run_id=run.id, portal="casa", kind="parse", message="KeyError"),
    ])
    await db_session.commit()

    per_run = (await client.get(f"/api/v1/scrape/runs/{run.id}/errors")).json()
    assert len(per_run) == 2
    blocked = (await client.get("/api/v1/scrape/errors", params={"kind": "blocked"})).json()
    assert [e["status_code"] for e in blocked] == [403]
    assert (await client.get("/api/v1/scrape/runs/missing/errors")).status_code == 404


async def test_unversioned_alias_still_works_but_is_hidden(client):
    assert (await client.get("/api/stats")).status_code == 200
    assert (await client.get("/api/v1/stats")).status_code == 200
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "/api/v1/stats" in paths
    assert "/api/stats" not in paths


async def test_last_update_reports_partial_jobs_and_per_portal_dates(client, db_session, monkeypatch):
    from app.services import scrape_service

    monkeypatch.setattr(scrape_service, "enabled_portals", lambda: ["casa", "remax"])
    monkeypatch.setattr("app.api.scrape.enabled_portals", lambda: ["casa", "remax"])
    assert (await client.get("/api/v1/scrape/last-update")).json()["finished_at"] is None

    db_session.add_all([
        ScrapeRun(portal="casa", status="completed", started_at="2026-05-24T01:00:00+00:00",
                  finished_at="2026-05-24T02:00:00+00:00", job_id="full"),
        ScrapeRun(portal="remax", status="completed_with_errors", started_at="2026-05-24T01:00:00+00:00",
                  finished_at="2026-05-24T01:30:00+00:00", job_id="full"),
        ScrapeRun(portal="remax", status="completed", started_at="2026-10-13T15:32:00+00:00",
                  finished_at="2026-10-13T15:39:00+00:00", job_id="partial"),
        ScrapeRun(portal="casa", status="failed", started_at="2026-10-14T08:00:00+00:00",
                  finished_at="2026-10-14T08:01:00+00:00", job_id="broken"),
    ])
    await db_session.commit()

    body = (await client.get("/api/v1/scrape/last-update")).json()
    assert body["finished_at"] == "2026-10-13T15:39:00+00:00"  # the failed run doesn't count
    assert (body["portals"], body["is_full"]) == (["remax"], False)
    assert body["by_portal"] == {
        "casa": "2026-05-24T02:00:00+00:00",
        "remax": "2026-10-13T15:39:00+00:00",
    }
