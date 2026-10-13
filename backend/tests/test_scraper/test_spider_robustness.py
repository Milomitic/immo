"""BaseSpider fetch/retry/circuit-breaker and coverage tracking, plus the
runner's deactivation gating — all offline with a scripted fake client."""

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.listing import Listing
from app.models.scrape_run import ScrapeError, ScrapeRun
from scraper import runner
from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.rate_limiter import RateLimiter
from tests.conftest import make_listing


class FakeResponse:
    def __init__(self, status: int, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class FakeClient:
    """Returns scripted responses per URL (a list is consumed in order;
    the last entry repeats). Exceptions in the script are raised."""

    def __init__(self, script: dict):
        self.script = {k: list(v) if isinstance(v, list) else [v] for k, v in script.items()}
        self.calls: list[str] = []

    async def get(self, url, **_):
        self.calls.append(url)
        seq = self.script.get(url) or [FakeResponse(404)]
        resp = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def close(self):
        pass


class FakeSpider(BaseSpider):
    portal_name = "fake"
    base_url = "https://fake.test"

    def __init__(self, client: FakeClient, site_pages: int = 1):
        super().__init__(rate_limiter=RateLimiter(requests_per_minute=60000))
        self._fake = client
        self.site_pages = site_pages

    async def _get_client(self):
        return self._fake

    async def build_search_url(self, params, page):
        return f"https://fake.test/search?page={page}"

    async def parse_search_results(self, html):
        return [u for u in html.split() if u.startswith("https://fake.test/l/")]

    async def get_total_pages(self, html):
        return self.site_pages

    async def parse_listing(self, url, html):
        sid = url.rsplit("/", 1)[1]
        return ListingItem(source_portal="fake", source_id=sid, source_url=url, title=html,
                           city="bari", property_type="apartment", listing_type="sale",
                           price=100000.0, lat=41.12, lng=16.87)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(*_args, **_kwargs):
        return None
    monkeypatch.setattr(BaseSpider, "_backoff", staticmethod(instant))
    monkeypatch.setattr("scraper.spiders.base.asyncio.sleep", instant)


# ------------------------------------------------------------------ fetch


async def test_transient_5xx_is_retried():
    url = "https://fake.test/x"
    client = FakeClient({url: [FakeResponse(503), FakeResponse(200, "ok")]})
    spider = FakeSpider(client)
    assert await spider.fetch(url) == "ok"
    assert len(client.calls) == 2
    assert spider.errors == []


async def test_network_error_is_retried():
    url = "https://fake.test/x"
    client = FakeClient({url: [ConnectionError("reset"), FakeResponse(200, "ok")]})
    assert await FakeSpider(client).fetch(url) == "ok"


async def test_404_is_informational_and_not_a_failure():
    url = "https://fake.test/gone"
    spider = FakeSpider(FakeClient({url: FakeResponse(404)}))
    assert await spider.fetch(url) is None
    assert (spider.errors[0]["kind"], spider.errors[0]["status_code"]) == ("gone", 404)
    assert spider._consecutive_failures == 0


async def test_404_on_a_search_page_is_a_failure():
    url = "https://fake.test/search?page=1"
    spider = FakeSpider(FakeClient({url: FakeResponse(404)}))
    assert await spider.fetch(url, not_found_ok=False) is None
    assert (spider.errors[0]["kind"], spider.errors[0]["status_code"]) == ("http", 404)
    assert spider._consecutive_failures == 1


async def test_403_retries_once_on_a_fresh_session():
    url = "https://fake.test/x"
    client = FakeClient({url: FakeResponse(403)})
    spider = FakeSpider(client)
    assert await spider.fetch(url) is None
    assert len(client.calls) == 2  # original + one retry, not the full budget
    assert spider.errors[-1]["kind"] == "blocked"


async def test_circuit_breaker_stops_hammering(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_CIRCUIT_BREAKER_THRESHOLD", 3)
    urls = [f"https://fake.test/{i}" for i in range(10)]
    client = FakeClient({u: FakeResponse(403) for u in urls})
    spider = FakeSpider(client)
    for u in urls:
        await spider.fetch(u)
    assert spider.circuit_open
    calls_when_open = len(client.calls)
    await spider.fetch("https://fake.test/another")
    assert len(client.calls) == calls_when_open  # no request once open
    assert not spider.coverage_complete


async def test_success_resets_failure_streak(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_CIRCUIT_BREAKER_THRESHOLD", 3)
    bad, good = "https://fake.test/bad", "https://fake.test/good"
    client = FakeClient({bad: FakeResponse(500), good: FakeResponse(200, "ok")})
    spider = FakeSpider(client)
    await spider.fetch(bad)
    await spider.fetch(bad)
    await spider.fetch(good)
    await spider.fetch(bad)
    assert not spider.circuit_open


# --------------------------------------------------------------- coverage


def _search_script(pages: int, per_page: int = 2) -> dict:
    script = {}
    n = 0
    for p in range(1, pages + 1):
        links = []
        for _ in range(per_page):
            n += 1
            url = f"https://fake.test/l/{n}"
            links.append(url)
            script[url] = FakeResponse(200, f"Listing {n}")
        script[f"https://fake.test/search?page={p}"] = FakeResponse(200, " ".join(links))
    return script


async def test_full_coverage_when_all_pages_walked():
    spider = FakeSpider(FakeClient(_search_script(3)), site_pages=3)
    items = [i async for i in spider.run(SearchParams(max_pages=10))]
    assert len(items) == 6
    assert spider.listings_seen == 6
    assert spider.coverage_complete


async def test_truncated_when_site_has_more_pages_than_cap():
    spider = FakeSpider(FakeClient(_search_script(5)), site_pages=5)
    [i async for i in spider.run(SearchParams(max_pages=2))]
    assert spider.search_truncated
    assert not spider.coverage_complete


class RecordingReporter:
    def __init__(self):
        self.events: list[tuple] = []

    def set_phase(self, phase):
        self.events.append(("phase", phase))

    def set_total(self, total):
        self.events.append(("total", total))

    def advance(self, n=1):
        self.events.append(("advance", n))

    def set_description(self, text):
        pass


async def test_search_pages_drive_progress():
    # Without this the UI showed "0 / 0" for the whole search phase.
    script = _search_script(3)
    script["https://fake.test/search?page=2"] = FakeResponse(500)  # failed pages count too
    spider = FakeSpider(FakeClient(script), site_pages=3)
    spider.progress = rec = RecordingReporter()
    [i async for i in spider.run(SearchParams(max_pages=10))]
    search = rec.events[: rec.events.index(("phase", "fetch"))]
    assert search == [("phase", "search"), ("total", 3), ("advance", 1), ("advance", 1), ("advance", 1)]


async def test_failed_search_page_breaks_coverage():
    script = _search_script(3)
    script["https://fake.test/search?page=2"] = FakeResponse(500)
    spider = FakeSpider(FakeClient(script), site_pages=3)
    [i async for i in spider.run(SearchParams(max_pages=10))]
    assert spider.search_pages_failed == 1
    assert not spider.coverage_complete


# ------------------------------------------------- runner: deactivation gate


@pytest.fixture
def fake_portal(monkeypatch):
    """Register a FakeSpider factory under the 'fake' portal key."""
    holder = {}

    def factory(**kwargs):
        spider = FakeSpider(holder["client"], site_pages=holder["pages"])
        spider.progress = kwargs.get("progress") or spider.progress
        return spider

    monkeypatch.setitem(runner.SPIDERS, "fake", factory)
    return holder


async def _seed_stale(session_factory):
    async with session_factory() as s:
        s.add(make_listing(source_portal="fake", source_id="stale",
                           last_seen_at="2020-01-01T00:00:00+00:00"))
        await s.commit()


async def _stale_active(session_factory) -> bool:
    async with session_factory() as s:
        row = (await s.execute(select(Listing).where(Listing.source_id == "stale"))).scalar_one()
        return row.is_active


async def test_stale_listing_deactivated_after_full_coverage(fake_portal, session_factory):
    await _seed_stale(session_factory)
    fake_portal.update(client=FakeClient(_search_script(2)), pages=2)

    await runner.run_spider("fake", "bari", "sale")

    assert await _stale_active(session_factory) is False
    async with session_factory() as s:
        run = (await s.execute(select(ScrapeRun))).scalar_one()
    assert run.coverage_complete is True
    assert run.listings_seen == 4
    assert run.listings_deactivated == 1


async def test_full_bari_scan_leaves_other_cities_alone(fake_portal, session_factory):
    async with session_factory() as s:
        s.add(make_listing(source_portal="fake", source_id="milano-stale", city="milano",
                           last_seen_at="2020-01-01T00:00:00+00:00"))
        await s.commit()
    fake_portal.update(client=FakeClient(_search_script(2)), pages=2)

    await runner.run_spider("fake", "bari", "sale")

    async with session_factory() as s:
        row = (await s.execute(select(Listing).where(Listing.source_id == "milano-stale"))).scalar_one()
        run = (await s.execute(select(ScrapeRun))).scalar_one()
    assert run.coverage_complete is True
    assert row.is_active is True
    assert run.listings_deactivated == 0


async def test_no_deactivation_with_partial_coverage(fake_portal, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_MAX_PAGES", 1)
    await _seed_stale(session_factory)
    fake_portal.update(client=FakeClient(_search_script(3)), pages=3)

    await runner.run_spider("fake", "bari", "sale")

    assert await _stale_active(session_factory) is True
    async with session_factory() as s:
        run = (await s.execute(select(ScrapeRun))).scalar_one()
    assert run.coverage_complete is False


async def test_errors_are_persisted_per_run(fake_portal, session_factory):
    script = _search_script(1)
    script["https://fake.test/l/2"] = FakeResponse(500)
    fake_portal.update(client=FakeClient(script), pages=1)

    await runner.run_spider("fake", "bari", "sale")

    async with session_factory() as s:
        errors = (await s.execute(select(ScrapeError))).scalars().all()
        run = (await s.execute(select(ScrapeRun))).scalar_one()
    assert [(e.kind, e.status_code) for e in errors] == [("http", 500)]
    assert run.status == "completed_with_errors"


async def test_removed_listing_does_not_fail_the_run(fake_portal, session_factory):
    script = _search_script(1)
    script["https://fake.test/l/2"] = FakeResponse(404)
    fake_portal.update(client=FakeClient(script), pages=1)

    await runner.run_spider("fake", "bari", "sale")

    async with session_factory() as s:
        run = (await s.execute(select(ScrapeRun))).scalar_one()
        errors = (await s.execute(select(ScrapeError))).scalars().all()
    assert run.status == "completed"
    assert [(e.kind, e.status_code) for e in errors] == [("gone", 404)]


async def test_vanished_search_page_fails_the_run(fake_portal, session_factory):
    # What remax's redesign looked like: the search URL itself 404s. That
    # must surface as a failed run, not a healthy one with 0 listings.
    fake_portal.update(client=FakeClient({}), pages=1)

    await runner.run_spider("fake", "bari", "sale")

    async with session_factory() as s:
        run = (await s.execute(select(ScrapeRun))).scalar_one()
        errors = (await s.execute(select(ScrapeError))).scalars().all()
    assert run.status == "completed_with_errors"
    assert run.coverage_complete is False
    assert [(e.kind, e.status_code) for e in errors] == [("http", 404)]


async def test_search_page_without_listings_is_reported(fake_portal, session_factory):
    fake_portal.update(
        client=FakeClient({"https://fake.test/search?page=1": FakeResponse(200, "<html/>")}), pages=1
    )

    await runner.run_spider("fake", "bari", "sale")

    async with session_factory() as s:
        run = (await s.execute(select(ScrapeRun))).scalar_one()
        errors = (await s.execute(select(ScrapeError))).scalars().all()
    assert run.status == "completed_with_errors"
    assert [e.kind for e in errors] == ["parse"]
