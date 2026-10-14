"""
TrovaCasa.it spider — the Immobiliare.it group's second portal.

Its listings largely repeat Immobiliare.it's, which we already have in
full, so the spider is frugal: it never opens a listing. The search cards
carry what's needed — type, town and street in the title ("Appartamento a
Bari via Vitantonio Di Cagno, 6"), neighbourhood, m², rooms, price, the
start of the description, feature tags and the photo ids. A scan of Bari is
~125 pages instead of ~3,000 detail requests. Cards have no coordinates:
the street places them on the map (app.services.geolocate).

* Search: ``/case-in-{vendita|affitto}/{city}?page=N``, 24 cards per page;
  the ``<h1>`` holds the total ("2.970 Case in vendita a Bari").
* Known ads are only reported (last seen, card price), never re-parsed.

Some of the site's text is double-encoded UTF-8 ("Ã¨" for "è"): repaired.
"""

import math
import re

import structlog
from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import (
    detect_feature,
    fix_mojibake,
    map_property_type,
    parse_float_text,
    parse_int,
)

logger = structlog.get_logger()

PAGE_SIZE = 24
_ID_RE = re.compile(r"/annunci/[a-z]+-[a-z]+-\d+-(\d+)")
_COUNT_RE = re.compile(r"(\d[\d.]*)")
_PHOTO_URL = "https://cdn.trovacasa.it/annunci/xxl/{}/foto.jpg"
# Tag → amenity. Tags not listed say nothing either way.
_TAGS = {
    "ascensore": "has_elevator",
    "balcone": "has_balcony",
    "terrazzo": "has_terrace",
    "terrazza": "has_terrace",
    "posto auto": "has_garage",
    "box": "has_garage",
    "garage": "has_garage",
    "giardino": "has_garden",
}


def _city_slug(city: str) -> str:
    return re.sub(r"[\s']+", "-", city.strip().lower())


def _price(text: str | None) -> float | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return float(digits) if digits and int(digits) > 0 else None


def _address(title: str, city: str) -> str | None:
    """What follows the town in the title: "Appartamento a Bari via X, 6" → "via X, 6"."""
    m = re.search(rf"\ba\s+{re.escape(city)}\b\s*(.*)$", title, re.IGNORECASE)
    rest = (m.group(1) if m else "").strip(" ,-")
    # Agencies sometimes repeat the town: "bari michelangelo signorile,28".
    rest = re.sub(rf"^{re.escape(city)}\s+", "", rest, flags=re.IGNORECASE).strip()
    return rest or None


class TrovacasaSpider(BaseSpider):
    portal_name = "trovacasa"
    base_url = "https://www.trovacasa.it"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._city = "bari"
        self._listing_type = "sale"
        self._parsed: dict[str, ListingItem] = {}

    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        m = _ID_RE.search(url)
        return m.group(1) if m else None

    async def run(self, params: SearchParams):
        self._city = params.city
        self._listing_type = params.listing_type
        logger.info("spider_start", portal=self.portal_name, city=params.city)
        url_prices = await self.search_phase(params)
        if url_prices is None:
            return

        # No detail phase: the cards are the listings.
        self.listings_seen = len(url_prices)
        known = params.known_source_ids or set()
        for url, price in url_prices.items():
            item = self._parsed.get(url)
            if item is None:
                continue
            if item.source_id in known:
                self.known_skipped_ids.append(item.source_id)
                self.observed_urls[item.source_id] = url
                if price is not None:
                    self.observed_prices[item.source_id] = price
            else:
                yield item
        self.progress.set_phase("done")
        logger.info("spider_done", portal=self.portal_name)

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        contract = "affitto" if params.listing_type == "rent" else "vendita"
        url = f"{self.base_url}/case-in-{contract}/{_city_slug(params.city)}"
        return f"{url}?page={page}" if page > 1 else url

    async def get_total_pages(self, html: str) -> int:
        h1 = BeautifulSoup(html, "lxml").select_one("h1")
        m = _COUNT_RE.search(h1.get_text(" ", strip=True)) if h1 else None
        if m:
            return max(1, math.ceil(int(m.group(1).replace(".", "")) / PAGE_SIZE))
        pages = [int(p) for p in re.findall(r"[?&]page=(\d+)", html)]
        return max(pages, default=1)

    async def parse_search_results(self, html: str) -> list[str]:
        return [url for url, _ in await self.parse_search_results_with_prices(html)]

    async def parse_search_results_with_prices(self, html: str) -> list[tuple[str, float | None]]:
        out = []
        for card in BeautifulSoup(html, "lxml").select(".immobileListing__card"):
            try:
                item = self._card_item(card)
            except (AttributeError, TypeError, ValueError) as e:
                self.record_error("parse", None, None, f"{type(e).__name__}: {e}")
                continue
            if item is None:
                continue
            self._parsed[item.source_url] = item
            out.append((item.source_url, item.price))
        return out

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        """Unused: TrovaCasa listings are built from the search cards."""
        return None

    def _card_item(self, card) -> ListingItem | None:
        link = card.select_one("a.card__title")
        href = link.get("href", "") if link else ""
        source_id = self._extract_source_id_from_url(href)
        if not source_id:
            return None
        title = fix_mojibake(link.get_text(" ", strip=True))
        zone = card.select_one(".card__quartiere")
        description = card.select_one(".card__description")
        price = card.select_one(".card__price")

        area = rooms = None
        for info in card.select(".card__info"):
            text = info.get_text(" ", strip=True).lower()
            if "m²" in text or "mq" in text:
                area = parse_float_text(text)
            elif "local" in text:
                rooms = parse_int(text)

        tags = [fix_mojibake(t.get_text(" ", strip=True)).lower() for t in card.select(".annuncioTag")]
        body = fix_mojibake(description.get_text(" ", strip=True)) if description else ""
        flags: dict[str, bool | None] = {}
        for tag in tags:
            for word, field in _TAGS.items():
                if word in tag:
                    flags[field] = True
        heating = next((t.replace("riscaldamento", "").strip().capitalize()
                        for t in tags if t.startswith("riscaldamento")), None)

        photo_ids = [p for p in (card.select_one("[data-src-list]") or {}).get("data-src-list", "").split("|") if p]
        return ListingItem(
            source_portal="trovacasa",
            source_id=source_id,
            source_url=f"{self.base_url}{href}",
            title=title,
            description=body or None,  # the card's excerpt: the page isn't opened
            price=_price(price.get_text() if price else None),
            area_sqm=area,
            rooms=rooms,
            address=_address(title, self._city),
            city=self._city.strip().lower(),
            zone=fix_mojibake(zone.get_text(" ", strip=True)) if zone and zone.get_text(strip=True) else None,
            property_type=map_property_type(title),
            listing_type="rent" if self._listing_type == "rent" else "sale",
            images=[_PHOTO_URL.format(p) for p in photo_ids[:30]],
            heating=heating or None,
            has_elevator=flags.get("has_elevator") or detect_feature(body, "ascensore"),
            has_balcony=flags.get("has_balcony") or detect_feature(body, "balcon"),
            has_terrace=flags.get("has_terrace") or detect_feature(body, "terrazz"),
            has_garage=flags.get("has_garage") or detect_feature(body, "garage", "box auto", "posto auto"),
            has_garden=flags.get("has_garden") or detect_feature(body, "giardin"),
            is_auction=bool(re.search(r"\basta\b", title, re.IGNORECASE)),
            raw_data={"tags": tags},
        )
