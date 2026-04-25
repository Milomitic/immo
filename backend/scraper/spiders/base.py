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
    # source_ids to skip detail-fetching for (already refreshed recently).
    # The spider still records them in its yield stream so last_seen_at
    # can be bumped, but it skips the expensive HTTP round-trip.
    fresh_source_ids: set[str] = field(default_factory=set)


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
        # source_ids that were skipped because a fresh canonical row already
        # exists. Runner bumps last_seen_at for these after the generator
        # drains, instead of yielding stubs through the pipeline.
        self.fresh_skipped_ids: list[str] = []

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

        listing_urls: list[str] = list(await self.parse_search_results(first_html))
        self.progress.set_description(
            f"{self.portal_name} cerca pag 1/{total_pages} ({len(listing_urls)} url)"
        )
        for page in range(2, total_pages + 1):
            search_url = await self.build_search_url(params, page)
            search_html = await self.fetch(search_url)
            if not search_html:
                continue
            page_urls = await self.parse_search_results(search_html)
            listing_urls.extend(page_urls)
            self.progress.set_description(
                f"{self.portal_name} cerca pag {page}/{total_pages} ({len(listing_urls)} url)"
            )

        # Dedupe URLs — some search pages repeat cards across paginations.
        seen: set[str] = set()
        unique_urls: list[str] = []
        for u in listing_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
        listing_urls = unique_urls
        logger.info("listings_collected", portal=self.portal_name, total=len(listing_urls))

        if not listing_urls:
            logger.info("spider_done", portal=self.portal_name)
            return

        # Fresh-skip: separate URLs whose source_id is in the fresh set.
        # We don't yield anything for them; the runner bumps last_seen_at
        # once the generator drains.
        fresh_ids = params.fresh_source_ids or set()
        to_fetch: list[str] = []
        for url in listing_urls:
            sid = self._extract_source_id_from_url(url)
            if sid and sid in fresh_ids:
                self.fresh_skipped_ids.append(sid)
            else:
                to_fetch.append(url)

        if self.fresh_skipped_ids:
            logger.info(
                "fresh_skipped",
                portal=self.portal_name,
                count=len(self.fresh_skipped_ids),
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
