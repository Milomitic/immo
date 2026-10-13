import asyncio
import random
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Protocol

import structlog
from curl_cffi.requests import AsyncSession

from app.config import settings
from scraper.items import ListingItem
from scraper.utils.rate_limiter import RateLimiter

logger = structlog.get_logger()


class ProgressReporter(Protocol):
    """Minimal interface spiders use to report progress.
    Implementations (rich-based bars, log-only, no-op) are plugged in by
    the runner so the spiders don't depend on any UI library.
    """

    def set_phase(self, phase: str) -> None: ...
    def set_total(self, total: int) -> None: ...
    def advance(self, n: int = 1) -> None: ...
    def set_description(self, text: str) -> None: ...


class _NullReporter:
    def set_phase(self, phase: str) -> None: pass
    def set_total(self, total: int) -> None: pass
    def advance(self, n: int = 1) -> None: pass
    def set_description(self, text: str) -> None: pass

# Matches trailing numeric IDs in agency-style URLs, e.g.
#   /immobili/1234567/
#   /scheda/9876543.html
#   /annuncio/12345
# Spiders with other URL shapes override _extract_source_id_from_url.
_URL_ID_RE = re.compile(r"/(\d{4,})(?:[/?.]|$)")


@dataclass
class SearchParams:
    # Default matches settings.SCRAPE_DEFAULT_CITY so direct callers (tests,
    # ad-hoc scripts) stay consistent with the production runner.
    city: str = "bari"
    listing_type: str = "sale"  # sale | rent
    property_type: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    rooms_min: int | None = None
    max_pages: int = field(default_factory=lambda: settings.SCRAPE_MAX_PAGES)
    # source_ids the spider should skip detail-fetching for — populated by
    # the runner from `pipeline.get_known_source_ids(portal)`. The spider
    # still records them in `known_skipped_ids` so last_seen_at can be
    # bumped, but it avoids the expensive HTTP round-trip. First snapshot
    # is treated as immutable: existing rows are NOT overwritten on
    # subsequent runs.
    known_source_ids: set[str] = field(default_factory=set)


class BaseSpider(ABC):
    portal_name: str = ""
    base_url: str = ""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        delay_min: float = 2.0,
        delay_max: float = 5.0,
        concurrency: int = 4,
        progress: ProgressReporter | None = None,
    ):
        self.rate_limiter = rate_limiter
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.concurrency = max(1, concurrency)
        self._detail_sem: asyncio.Semaphore | None = None
        self.client: AsyncSession | None = None
        self._client_lock = asyncio.Lock()
        self.progress: ProgressReporter = progress or _NullReporter()
        # source_ids that were skipped because the listing is already in DB.
        # Runner calls `bump_last_seen` for these after the generator drains
        # so the inactivity-detection clock keeps ticking.
        self.known_skipped_ids: list[str] = []
        # Latest price observed on the search card for each known source_id,
        # populated when the spider's parse_search_results_with_prices
        # returns a non-None price. Runner uses this to detect price
        # changes without a detail-page fetch.
        self.observed_prices: dict[str, float] = {}
        # Current URL of each known source_id. Portals move listings to new
        # URL schemes (remax did in 2026); the runner refreshes stored links
        # so "open on portal" doesn't 404. Content stays immutable.
        self.observed_urls: dict[str, str] = {}

        # --- Health & coverage, read by the runner after the run.
        # Structured failures, persisted to the scrape_errors table.
        self.errors: list[dict] = []
        self._consecutive_failures = 0
        # Tripped after SCRAPE_CIRCUIT_BREAKER_THRESHOLD consecutive failed
        # requests: the portal is blocking us or down, so every further
        # fetch returns None immediately instead of deepening a ban.
        self.circuit_open = False
        # True when the site has more result pages than we're allowed to
        # walk, or a search page failed — either way we didn't see the
        # whole catalog and must not infer "gone" from "not seen".
        self.search_truncated = False
        self.search_pages_failed = 0
        # Distinct listings observed on search pages (new + known).
        self.listings_seen = 0
        # Sessions replaced after a 403. Not closed on the spot: other
        # concurrent fetches may still be using them mid-request.
        self._retired_clients: list[AsyncSession] = []

    @property
    def coverage_complete(self) -> bool:
        return not (self.search_truncated or self.search_pages_failed or self.circuit_open)

    async def _get_client(self) -> AsyncSession:
        if self.client is None:
            async with self._client_lock:
                if self.client is None:
                    # impersonate="chrome" already sets all correct browser headers
                    # Adding manual Sec-* headers conflicts and causes 403s
                    self.client = AsyncSession(impersonate="chrome", timeout=30)
        return self.client

    async def _rotate_session(self) -> None:
        """Start a fresh session (new cookies/TLS state) for later requests
        without closing the old one under concurrent in-flight fetches."""
        async with self._client_lock:
            if self.client is not None:
                self._retired_clients.append(self.client)
                self.client = None

    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        """Return the source_id embedded in a listing URL, if the spider's
        URL format allows it. Default grabs the last numeric segment (>=4
        digits), which matches the agency-style URL convention used by
        casa / tecnocasa / remax / gabetti. Subclasses can override.
        """
        m = _URL_ID_RE.search(url)
        return m.group(1) if m else None

    async def close(self) -> None:
        for c in [self.client, *self._retired_clients]:
            if c is not None:
                try:
                    await c.close()
                except Exception:
                    pass
        self.client = None
        self._retired_clients.clear()

    # Cap stored errors so a portal failing on thousands of URLs can't
    # balloon memory or the scrape_errors table.
    _MAX_ERRORS = 300

    def record_error(self, kind: str, url: str | None, status: int | None, message: str) -> None:
        if len(self.errors) < self._MAX_ERRORS:
            self.errors.append(
                {"kind": kind, "url": url, "status_code": status, "message": message[:500]}
            )

    def _register_failure(self, kind: str, url: str, status: int | None, message: str) -> None:
        self.record_error(kind, url, status, message)
        logger.warning("fetch_failed", portal=self.portal_name, url=url, kind=kind, status=status)
        self._consecutive_failures += 1
        if not self.circuit_open and self._consecutive_failures >= settings.SCRAPE_CIRCUIT_BREAKER_THRESHOLD:
            self.circuit_open = True
            self.record_error(
                "blocked", None, status,
                f"circuit breaker open after {self._consecutive_failures} consecutive failures",
            )
            logger.error("circuit_open", portal=self.portal_name, failures=self._consecutive_failures)

    @staticmethod
    async def _backoff(attempt: int, base: float) -> None:
        # Exponential with ±25% jitter so concurrent tasks don't retry in lockstep.
        await asyncio.sleep(base * (2 ** attempt) * random.uniform(0.75, 1.25))

    async def fetch(self, url: str, retries: int = 3, *, not_found_ok: bool = True) -> str | None:
        """GET with retries. Transient failures (network, 5xx) back off
        exponentially; 429 honours Retry-After; 403 gets one retry on a
        fresh session.

        On a detail page 404/410 means the listing was removed: recorded as
        kind "gone", not a portal health problem. Search pages pass
        ``not_found_ok=False`` — a missing search page means the portal
        changed its URL scheme, which is a real failure."""
        if self.circuit_open:
            return None

        for attempt in range(retries + 1):
            # Every attempt goes through the limiter — retries must not
            # bypass the per-portal request budget.
            await self.rate_limiter.acquire(self.portal_name)
            try:
                client = await self._get_client()
                response = await client.get(url)
            except Exception as e:
                if attempt < retries:
                    await self._backoff(attempt, base=2.0)
                    continue
                self._register_failure("network", url, None, str(e))
                return None

            status = response.status_code
            if status < 400:
                self._consecutive_failures = 0
                return response.text

            if status in (404, 410) and not_found_ok:
                self.record_error("gone", url, status, "listing removed")
                return None

            if status == 403 and attempt < min(retries, 1):
                await self._rotate_session()
                await self._backoff(attempt, base=8.0)
                continue

            if status == 429 and attempt < retries:
                retry_after = response.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.isdigit() else 30.0
                await asyncio.sleep(min(wait, 120.0))
                continue

            if status >= 500 and attempt < retries:
                await self._backoff(attempt, base=2.0)
                continue

            kind = "blocked" if status in (403, 429) else "http"
            self._register_failure(kind, url, status, f"HTTP {status}")
            return None

        return None

    @abstractmethod
    async def build_search_url(self, params: SearchParams, page: int) -> str:
        ...

    @abstractmethod
    async def parse_search_results(self, html: str) -> list[str]:
        """Parse search results page, return listing URLs."""
        ...

    async def parse_search_results_with_prices(
        self, html: str
    ) -> list[tuple[str, float | None]]:
        """Same as ``parse_search_results`` but each entry is paired with
        the price displayed on the search card, when extractable.

        Override in spiders that can read the price off the listing card
        without a detail-page fetch — used to detect price changes on
        already-known listings without paying for an extra HTTP request.
        Default: returns each URL with ``None`` (price-change detection
        disabled for that spider).
        """
        urls = await self.parse_search_results(html)
        return [(u, None) for u in urls]

    @abstractmethod
    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        """Parse a single listing page into a ListingItem."""
        ...

    @abstractmethod
    async def get_total_pages(self, html: str) -> int:
        """Get total number of result pages from search results."""
        ...

    async def run(self, params: SearchParams) -> AsyncGenerator[ListingItem, None]:
        """Two-phase run: collect URLs from search pages, then fetch details
        concurrently bounded by `self.concurrency`. RateLimiter still caps
        requests-per-minute, so concurrency just fills that budget in
        parallel instead of serially.
        """
        logger.info("spider_start", portal=self.portal_name, city=params.city)
        url_prices = await self.search_phase(params)
        if url_prices is None:
            return
        async for item in self.detail_phase(url_prices, params):
            yield item

    async def search_phase(self, params: SearchParams) -> dict[str, float | None] | None:
        """Phase 1: walk the result pages built by ``build_search_url``.

        Returns each listing URL with the price shown on its card (None when
        the card has none), or None when the first page couldn't be loaded
        (already recorded). Spiders whose catalogue spans several result
        lists call it once per list and merge the results.
        """
        self.progress.set_phase("search")
        self.progress.set_description(f"{self.portal_name} cerca pag 1")

        # Collect all listing URLs sequentially (few pages, cheap).
        first_url = await self.build_search_url(params, page=1)
        first_html = await self.fetch(first_url, not_found_ok=False)
        if not first_html:
            logger.error("search_failed", portal=self.portal_name, url=first_url)
            self.search_pages_failed += 1
            self.progress.set_phase("failed")
            return None

        site_pages = await self.get_total_pages(first_html)
        total_pages = min(site_pages, params.max_pages)
        self.search_truncated = site_pages > params.max_pages
        logger.info("pages_found", portal=self.portal_name, total_pages=total_pages,
                    site_pages=site_pages)
        # Search pages are the progress unit of this phase (the UI shows
        # "12 / 37" instead of an empty bar until detail fetching starts).
        self.progress.set_total(total_pages)
        self.progress.advance()

        # parse_search_results_with_prices returns [(url, price_or_none), ...].
        # Spiders that can read the price off the card override it; others
        # fall back to the abstract parse_search_results and emit None
        # prices. We dedupe by URL, keeping the first non-None price.
        url_prices: dict[str, float | None] = {}
        for u, p in await self.parse_search_results_with_prices(first_html):
            if u not in url_prices or (url_prices[u] is None and p is not None):
                url_prices[u] = p
        if not url_prices:
            # Page served but nothing parsed: almost always a layout change.
            self.record_error("parse", first_url, None, "no listings parsed from first search page")
        self.progress.set_description(
            f"{self.portal_name} cerca pag 1/{total_pages} ({len(url_prices)} url)"
        )
        for page in range(2, total_pages + 1):
            if self.circuit_open:
                self.search_pages_failed += total_pages - page + 1
                break
            search_url = await self.build_search_url(params, page)
            search_html = await self.fetch(search_url, not_found_ok=False)
            self.progress.advance()
            if not search_html:
                self.search_pages_failed += 1
                continue
            for u, p in await self.parse_search_results_with_prices(search_html):
                if u not in url_prices or (url_prices[u] is None and p is not None):
                    url_prices[u] = p
            self.progress.set_description(
                f"{self.portal_name} cerca pag {page}/{total_pages} ({len(url_prices)} url)"
            )
        return url_prices

    async def detail_phase(
        self,
        url_prices: dict[str, float | None],
        params: SearchParams,
    ) -> AsyncGenerator[ListingItem, None]:
        """Phase 2, shared by every spider whose search yields listing URLs.

        Known listings are skipped (snapshot is immutable — the runner only
        bumps last_seen_at and diffs the card price); the rest are fetched
        concurrently, bounded by ``self.concurrency``.
        """
        listing_urls: list[str] = list(url_prices.keys())
        self.listings_seen = len(listing_urls)
        logger.info("listings_collected", portal=self.portal_name, total=len(listing_urls))

        if not listing_urls:
            self.progress.set_phase("done")
            logger.info("spider_done", portal=self.portal_name)
            return

        known_ids = params.known_source_ids or set()
        to_fetch: list[str] = []
        for url in listing_urls:
            sid = self._extract_source_id_from_url(url)
            if sid and sid in known_ids:
                self.known_skipped_ids.append(sid)
                self.observed_urls[sid] = url
                price = url_prices.get(url)
                if price is not None:
                    self.observed_prices[sid] = price
            else:
                to_fetch.append(url)

        if self.known_skipped_ids:
            logger.info(
                "known_skipped",
                portal=self.portal_name,
                count=len(self.known_skipped_ids),
                will_fetch=len(to_fetch),
            )

        if not to_fetch:
            self.progress.set_phase("done")
            logger.info("spider_done", portal=self.portal_name)
            return

        # Phase 2: parallel detail-fetch bounded by semaphore.
        self.progress.set_phase("fetch")
        self.progress.set_total(len(to_fetch))
        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_and_parse(url: str) -> ListingItem | None:
            async with sem:
                html = await self.fetch(url)
                if not html:
                    self.progress.advance()
                    return None
                try:
                    item = await self.parse_listing(url, html)
                except Exception as e:
                    logger.error("parse_error", portal=self.portal_name, url=url, error=str(e))
                    self.record_error("parse", url, None, f"{type(e).__name__}: {e}")
                    item = None
                self.progress.advance()
                return item

        tasks = [asyncio.create_task(fetch_and_parse(u)) for u in to_fetch]
        try:
            for coro in asyncio.as_completed(tasks):
                item = await coro
                if item:
                    yield item
        finally:
            # If the consumer broke early (exception, batch failure, the
            # runner losing interest) any pending tasks would keep running
            # in the background — potentially outliving the spider and
            # holding HTTP connections. Cancel + drain them here.
            pending = [t for t in tasks if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        self.progress.set_phase("done")
        logger.info("spider_done", portal=self.portal_name)
