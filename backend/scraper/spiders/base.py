import asyncio
import random
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Protocol

import structlog
from curl_cffi.requests import AsyncSession

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
# Same pattern used by scraper.utils.agency_parser.parse_agency_detail.
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
    max_pages: int = 50
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

    async def _get_client(self) -> AsyncSession:
        if self.client is None:
            async with self._client_lock:
                if self.client is None:
                    # impersonate="chrome" already sets all correct browser headers
                    # Adding manual Sec-* headers conflicts and causes 403s
                    self.client = AsyncSession(impersonate="chrome", timeout=30)
        return self.client

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
        if self.client:
            await self.client.close()
            self.client = None

    async def fetch(self, url: str, retries: int = 2) -> str | None:
        await self.rate_limiter.acquire(self.portal_name)

        for attempt in range(retries + 1):
            try:
                client = await self._get_client()
                response = await client.get(url)

                if response.status_code == 403:
                    if attempt < retries:
                        wait = random.uniform(5, 15)
                        logger.warning("got_403_retrying", portal=self.portal_name, url=url, attempt=attempt + 1, wait=round(wait, 1))
                        await self.close()
                        await asyncio.sleep(wait)
                        continue
                    logger.error("http_error", portal=self.portal_name, url=url, status=403)
                    return None

                if response.status_code == 429:
                    wait = random.uniform(30, 60)
                    logger.warning("rate_limited", portal=self.portal_name, url=url, wait=wait)
                    await asyncio.sleep(wait)
                    continue

                if response.status_code >= 400:
                    logger.error("http_error", portal=self.portal_name, url=url, status=response.status_code)
                    return None

                return response.text

            except Exception as e:
                if attempt < retries:
                    logger.warning("request_error_retrying", portal=self.portal_name, url=url, error=str(e), attempt=attempt + 1)
                    await self.close()
                    await asyncio.sleep(random.uniform(3, 8))
                    continue
                logger.error("request_error", portal=self.portal_name, url=url, error=str(e))
                return None

        return None

    async def _delay(self) -> None:
        delay = random.uniform(self.delay_min, self.delay_max)
        await asyncio.sleep(delay)

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
        self.progress.set_phase("search")
        self.progress.set_description(f"{self.portal_name} cerca pag 1")

        # Phase 1: collect all listing URLs sequentially (few pages, cheap).
        first_url = await self.build_search_url(params, page=1)
        first_html = await self.fetch(first_url)
        if not first_html:
            logger.error("search_failed", portal=self.portal_name, url=first_url)
            self.progress.set_phase("failed")
            return

        total_pages = await self.get_total_pages(first_html)
        total_pages = min(total_pages, params.max_pages)
        logger.info("pages_found", portal=self.portal_name, total_pages=total_pages)

        # parse_search_results_with_prices returns [(url, price_or_none), ...].
        # Spiders that can read the price off the card override it; others
        # fall back to the abstract parse_search_results and emit None
        # prices. We dedupe by URL, keeping the first non-None price.
        url_prices: dict[str, float | None] = {}
        for u, p in await self.parse_search_results_with_prices(first_html):
            if u not in url_prices or (url_prices[u] is None and p is not None):
                url_prices[u] = p
        self.progress.set_description(
            f"{self.portal_name} cerca pag 1/{total_pages} ({len(url_prices)} url)"
        )
        for page in range(2, total_pages + 1):
            search_url = await self.build_search_url(params, page)
            search_html = await self.fetch(search_url)
            if not search_html:
                continue
            for u, p in await self.parse_search_results_with_prices(search_html):
                if u not in url_prices or (url_prices[u] is None and p is not None):
                    url_prices[u] = p
            self.progress.set_description(
                f"{self.portal_name} cerca pag {page}/{total_pages} ({len(url_prices)} url)"
            )

        listing_urls: list[str] = list(url_prices.keys())
        logger.info("listings_collected", portal=self.portal_name, total=len(listing_urls))

        if not listing_urls:
            logger.info("spider_done", portal=self.portal_name)
            return

        # Skip detail-fetch for any URL whose source_id is already in the
        # DB. We don't yield anything for them; the runner bumps
        # last_seen_at once the generator drains. First-observed snapshot
        # is preserved untouched. If the search card carried a price,
        # capture it in `observed_prices` — the runner uses that to spot
        # price changes on already-known listings without a detail fetch.
        known_ids = params.known_source_ids or set()
        to_fetch: list[str] = []
        for url in listing_urls:
            sid = self._extract_source_id_from_url(url)
            if sid and sid in known_ids:
                self.known_skipped_ids.append(sid)
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
