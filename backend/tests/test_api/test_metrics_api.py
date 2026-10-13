import httpx
import pytest
from prometheus_client.parser import text_string_to_metric_families

from app.config import settings
from app.main import app
from app.models.scrape_run import ScrapeError, ScrapeRun
from tests.conftest import make_listing


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _samples(text: str) -> dict[tuple, float]:
    """{(sample name, sorted labels): value} — parsing also proves the
    exposition is valid."""
    return {
        (s.name, tuple(sorted(s.labels.items()))): s.value
        for family in text_string_to_metric_families(text)
        for s in family.samples
    }


def _run(portal, status, started, finished, **kw):
    return ScrapeRun(portal=portal, status=status, started_at=started, finished_at=finished, **kw)


async def test_metrics_reports_catalogue_and_scrapes(client, db_session):
    db_session.add_all([
        make_listing(source_id="1"),
        make_listing(source_id="2", is_active=False),
        make_listing(source_id="3", source_portal="casa", listing_url="https://example.com/3"),
    ])
    older = _run("casa", "completed", "2026-10-01T10:00:00+00:00", "2026-10-01T10:05:00+00:00",
                 listings_seen=500, coverage_complete=True)
    latest = _run("casa", "failed", "2026-10-02T10:00:00+00:00", "2026-10-02T10:00:30+00:00",
                  listings_seen=0, coverage_complete=False)
    running = _run("immobiliare", "running", "2026-10-02T11:00:00+00:00", None)
    db_session.add_all([older, latest, running])
    await db_session.flush()
    db_session.add_all([
        ScrapeError(run_id=latest.id, portal="casa", kind="blocked"),
        ScrapeError(run_id=latest.id, portal="casa", kind="blocked"),
        ScrapeError(run_id=older.id, portal="casa", kind="gone"),
    ])
    await db_session.commit()

    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    m = _samples(r.text)

    assert m[("immo_listings", (("portal", "immobiliare"), ("state", "active")))] == 1
    assert m[("immo_listings", (("portal", "immobiliare"), ("state", "inactive")))] == 1
    assert m[("immo_listings", (("portal", "casa"), ("state", "active")))] == 1
    assert m[("immo_scrape_running", ())] == 1
    # the latest run is the failed one; the last *success* is the older one
    assert m[("immo_scrape_last_status", (("portal", "casa"), ("status", "failed")))] == 1
    assert m[("immo_scrape_last_status", (("portal", "casa"), ("status", "completed")))] == 0
    assert m[("immo_scrape_last_duration_seconds", (("portal", "casa"),))] == 30
    assert m[("immo_scrape_last_coverage_complete", (("portal", "casa"),))] == 0
    assert m[("immo_scrape_last_success_timestamp_seconds", (("portal", "casa"),))] == 1790849100
    assert m[("immo_scrape_errors_total", (("kind", "blocked"), ("portal", "casa")))] == 2
    assert m[("immo_scrape_errors_total", (("kind", "gone"), ("portal", "casa")))] == 1


async def test_request_latency_is_labelled_by_route_template(client):
    await client.get("/api/v1/listings/does-not-exist")
    await client.get("/api/listings/does-not-exist")
    await client.get("/no/such/path")
    await client.delete("/api/v1/stats")  # right path, wrong method: 405
    m = _samples((await client.get("/metrics")).text)

    by_route = {
        (dict(labels).get("method"), dict(labels).get("route")): dict(labels).get("status")
        for (name, labels) in m
        if name == "immo_http_request_duration_seconds_count"
    }
    assert by_route[("GET", "/api/v1/listings/{listing_id}")] == "4xx"
    assert by_route[("GET", "unmatched")] == "4xx"
    assert by_route[("DELETE", "unmatched")] == "4xx"  # no endpoint ran
    assert ("GET", "/metrics") in by_route
    # the unversioned alias keeps its own prefix
    assert by_route[("GET", "/api/listings/{listing_id}")] == "4xx"
    assert all(route != "/api/v1/listings/does-not-exist" for _, route in by_route)


async def test_metrics_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "METRICS_ENABLED", False)
    assert (await client.get("/metrics")).status_code == 404
