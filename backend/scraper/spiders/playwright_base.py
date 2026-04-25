import asyncio
import random
from abc import abstractmethod
from collections.abc import AsyncGenerator

import structlog
from playwright.async_api import async_playwright, Page, Browser

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.rate_limiter import RateLimiter

logger = structlog.get_logger()


class PlaywrightSpider(BaseSpider):
    """Spider that uses a real browser to bypass DataDome/anti-bot protections."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        delay_min: float = 3.0,
        delay_max: float = 7.0,
        headless: bool = True,
    ):
        super().__init__(rate_limiter, delay_min, delay_max)
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def _get_page(self) -> Page:
        if self._page is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="it-IT",
                timezone_id="Europe/Rome",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            # Remove webdriver flag
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            self._page = await context.new_page()
        return self._page

    async def close(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def fetch(self, url: str, retries: int = 2) -> str | None:
        await self.rate_limiter.acquire(self.portal_name)
        page = await self._get_page()

        for attempt in range(retries + 1):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if response is None:
                    logger.error("no_response", portal=self.portal_name, url=url)
                    return None

                # Wait for DataDome challenge to resolve
                await asyncio.sleep(random.uniform(2, 4))

                # Check if we got blocked
                status = response.status
                if status == 403:
                    content = await page.content()
                    if "datadome" in content.lower() or "captcha" in content.lower():
                        # Wait longer for JS challenge
                        logger.warning("datadome_challenge", portal=self.portal_name, url=url, attempt=attempt + 1)
                        await asyncio.sleep(random.uniform(5, 10))
                        content = await page.content()
                        if len(content) > 2000:  # Challenge likely resolved
                            return content

                    if attempt < retries:
                        await asyncio.sleep(random.uniform(8, 15))
                        continue
                    logger.error("http_error", portal=self.portal_name, url=url, status=403)
                    return None

                if status >= 400:
                    logger.error("http_error", portal=self.portal_name, url=url, status=status)
                    return None

                # Wait for content to load
                await page.wait_for_load_state("networkidle", timeout=10000)
                content = await page.content()
                return content

            except Exception as e:
                if attempt < retries:
                    logger.warning("fetch_error_retrying", portal=self.portal_name, url=url, error=str(e), attempt=attempt + 1)
                    await asyncio.sleep(random.uniform(5, 10))
                    continue
                logger.error("fetch_error", portal=self.portal_name, url=url, error=str(e))
                return None

        return None
