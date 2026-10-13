"""
Subito.it spider — the classifieds site where private sellers advertise.

Subito sits behind DataDome (the anti-bot that blocks Idealista), so this
spider is deliberately frugal: it never opens a listing page. The search
pages are Next.js, and their ``__NEXT_DATA__`` already carries each ad in
full — title, whole description, date, photos and the structured
features (size, rooms, bathrooms, floor, heating, condition, energy class,
lift, balcony, garden, parking). A scan of Bari is ~35 requests, at the
slow per-portal pace set in settings, instead of one per listing.

* Search: ``/annunci-{region}/{vendita|affitto}/{category}/{province}/{town}/?o=N``,
  30 ads per page, for apartments and for houses/villas.
* Known ads are only reported (last seen, card price), never re-parsed:
  the first snapshot is immutable, as for every portal.

What Subito doesn't give: an address or coordinates (only the town), so
these listings show in the lists but not on the map, and deduplication
can't use location (see dedup_service: such matches must be near-exact).
"""

import json
import math
import re

import structlog

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import detect_feature, map_condition, map_property_type

logger = structlog.get_logger()

PAGE_SIZE = 30
_CATEGORIES = ("appartamenti", "ville-singole-e-a-schiera")
_ID_RE = re.compile(r"-(\d+)\.htm")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_ENERGY_RE = re.compile(r"^[A-G]\d?\+*$")
# Photos: the page's own size rules. Stored at gallery size; the frontend
# swaps in the card rule for thumbnails.
_IMAGE_RULE = "gallery-desktop-2x-auto"

# Subito's location URLs need the region and the province of the town.
# Towns of the Bari area and Apulia's provincial capitals; add a line for
# another city ("town-slug": ("region", "province-slug")).
_AREAS: dict[str, tuple[str, str]] = {
    **{town: ("puglia", "bari") for town in (
        "bari", "acquaviva-delle-fonti", "adelfia", "alberobello", "altamura", "bitetto",
        "bitonto", "bitritto", "capurso", "casamassima", "cassano-delle-murge",
        "castellana-grotte", "cellamare", "conversano", "corato", "gioia-del-colle",
        "giovinazzo", "gravina-in-puglia", "grumo-appula", "locorotondo", "modugno",
        "mola-di-bari", "molfetta", "monopoli", "noci", "noicattaro", "palo-del-colle",
        "polignano-a-mare", "putignano", "rutigliano", "ruvo-di-puglia", "sammichele-di-bari",
        "sannicandro-di-bari", "santeramo-in-colle", "terlizzi", "toritto", "triggiano",
        "turi", "valenzano",
    )},
    "barletta": ("puglia", "barletta-andria-trani"),
    "andria": ("puglia", "barletta-andria-trani"),
    "trani": ("puglia", "barletta-andria-trani"),
    "brindisi": ("puglia", "brindisi"),
    "foggia": ("puglia", "foggia"),
    "lecce": ("puglia", "lecce"),
    "taranto": ("puglia", "taranto"),
}


def _slug(text: str) -> str:
    return re.sub(r"[\s']+", "-", text.strip().lower())


def _feature(card: dict, name: str) -> dict | None:
    """First value of a structured feature: ``{"key": "3", "value": "3"}``."""
    values = ((card.get("features") or {}).get(f"/{name}") or {}).get("values") or []
    return values[0] if values and isinstance(values[0], dict) else None


def _value(card: dict, name: str) -> str | None:
    v = _feature(card, name)
    return str(v.get("value")).strip() if v and v.get("value") not in (None, "") else None


def _number(card: dict, name: str, cast=float):
    v = _feature(card, name)
    try:
        n = cast(str(v["key"]).replace(",", ".")) if v else None
    except (TypeError, ValueError):
        return None
    return n if n and n > 0 else None


def _yes(card: dict, name: str) -> bool | None:
    """Subito's boolean fields are the seller's explicit answer."""
    v = _feature(card, name)
    if not v:
        return None
    return str(v.get("key")) == "1"


def _with_text(structured: bool | None, text: str, *keywords: str) -> bool | None:
    if structured is not None:
        return structured
    return detect_feature(text, *keywords) if text else None


def _parking(card: dict) -> bool | None:
    value = _value(card, "parking")
    if value is None:
        return None
    return "nessun" not in value.lower()


class SubitoSpider(BaseSpider):
    portal_name = "subito"
    base_url = "https://www.subito.it"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._category = _CATEGORIES[0]
        self._area: tuple[str, str, str] | None = None  # region, province, town
        self._listing_type = "sale"
        self._parsed: dict[str, ListingItem] = {}

    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        m = _ID_RE.search(url)
        return m.group(1) if m else None

    async def run(self, params: SearchParams):
        town = _slug(params.city)
        if town not in _AREAS:
            self.record_error("spider", None, None, f"città non mappata per Subito: {params.city!r} (vedi _AREAS)")
            self.search_pages_failed += 1
            self.progress.set_phase("failed")
            return
        self._area = (*_AREAS[town], town)
        self._listing_type = params.listing_type
        logger.info("spider_start", portal=self.portal_name, city=params.city)

        url_prices: dict[str, float | None] = {}
        walked_any = False
        for category in _CATEGORIES:
            self._category = category
            found = await self.search_phase(params)
            if found is None:
                continue
            walked_any = True
            url_prices.update(found)
        if not walked_any:
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
        region, province, town = self._area or ("puglia", "bari", _slug(params.city))
        contract = "affitto" if self._listing_type == "rent" else "vendita"
        url = f"{self.base_url}/annunci-{region}/{contract}/{self._category}/{province}/{town}/"
        return f"{url}?o={page}" if page > 1 else url

    @staticmethod
    def _items(html: str) -> dict:
        m = _NEXT_DATA_RE.search(html)
        if not m:
            return {}
        try:
            data = json.loads(m.group(1))
        except ValueError:
            return {}
        return (((data.get("props") or {}).get("pageProps") or {}).get("initialState") or {}).get("items") or {}

    async def get_total_pages(self, html: str) -> int:
        items = self._items(html)
        pages = items.get("totalPages")
        if isinstance(pages, int) and pages > 0:
            return pages
        return max(1, math.ceil((items.get("total") or 0) / PAGE_SIZE))

    async def parse_search_results(self, html: str) -> list[str]:
        return [url for url, _ in await self.parse_search_results_with_prices(html)]

    async def parse_search_results_with_prices(self, html: str) -> list[tuple[str, float | None]]:
        out = []
        # "originalList" is the search result; "galleryList" holds paid
        # placements from the wider area, left out.
        for card in self._items(html).get("originalList") or []:
            if not isinstance(card, dict) or card.get("kind") != "AdItem":
                continue
            try:
                item = self._card_item(card)
            except (KeyError, TypeError, ValueError) as e:
                self.record_error("parse", (card.get("urls") or {}).get("default"), None, f"{type(e).__name__}: {e}")
                continue
            if item is None:
                continue
            self._parsed[item.source_url] = item
            out.append((item.source_url, item.price))
        return out

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        """Unused: Subito listings are built from the search cards."""
        return None

    def _card_item(self, card: dict) -> ListingItem | None:
        url = (card.get("urls") or {}).get("default") or ""
        source_id = self._extract_source_id_from_url(url)
        if not source_id:
            return None
        geo = card.get("geo") or {}
        title = (card.get("subject") or "").strip() or "Annuncio Subito"
        body = (card.get("body") or "").strip() or None
        text = body or ""

        property_type = map_property_type(title)
        if self._category != "appartamenti" and property_type == "apartment":
            property_type = "villa"

        energy = (_value(card, "energy_class") or "").upper()
        images = [
            f"{img['cdnBaseUrl']}?rule={_IMAGE_RULE}"
            for img in card.get("images") or []
            if isinstance(img, dict) and str(img.get("cdnBaseUrl", "")).startswith("http")
        ]
        advertiser = card.get("advertiser") or {}

        return ListingItem(
            source_portal="subito",
            source_id=source_id,
            source_url=url,
            title=title,
            description=body,
            price=_number(card, "price"),
            area_sqm=_number(card, "size"),
            rooms=_number(card, "room", int),
            bathrooms=_number(card, "bathrooms", int),
            floor=_value(card, "floor"),
            city=((geo.get("town") or {}).get("value") or "").strip().lower(),
            province=(geo.get("city") or {}).get("shortName") or None,
            property_type=property_type,
            listing_type="rent" if self._listing_type == "rent" else "sale",
            images=images[:30],
            energy_class=energy if _ENERGY_RE.match(energy) else None,
            condition=map_condition(_value(card, "building_condition")),
            heating=_value(card, "heating"),
            has_elevator=_with_text(_yes(card, "elevator"), text, "ascensore"),
            has_balcony=_with_text(_yes(card, "balcony"), text, "balcon"),
            has_terrace=_with_text(None, text, "terrazz"),
            has_garage=_with_text(_parking(card), text, "garage", "box auto", "posto auto"),
            has_garden=_with_text(_yes(card, "garden"), text, "giardin"),
            publication_date=(card.get("date") or "")[:10] or None,
            raw_data={
                # Subito is where private sellers advertise: worth knowing.
                "advertiser": "agenzia" if advertiser.get("company") else "privato",
            },
        )
