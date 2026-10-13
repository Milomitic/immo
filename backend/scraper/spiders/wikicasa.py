"""
Wikicasa.it spider — agency listings and judicial auctions.

Wikicasa is a Nuxt 3 site: every page carries its data in the
``__NUXT_DATA__`` payload (see ``scraper.utils.nuxt``), as Pinia stores.

* Search: ``/{vendita|affitto|asta}-case/{city}/?p=N``, 25 cards per page.
  ``realEstateListingStoreId`` holds ``listingCount`` and the cards
  (``realEstateList``: id, url, price, …). Auctions are a separate list,
  walked after the sales.
* Detail: ``/annuncio/{id}``. ``realEstateDetailsStoreId.realEstate`` has
  the structured listing — every photo and floor plan, coordinates, floor,
  building year, amenities — and, for auctions, the sale's data (date, base
  price, minimum offer, court, procedure, Portale Vendite Pubbliche link,
  notice documents). Only the condition and heating are read from the
  rendered labels: the payload has them as numeric codes.
"""

import math
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import detect_feature, map_condition, map_property_type
from scraper.utils.nuxt import nuxt_payload, pinia_store

PAGE_SIZE = 25

# Result lists walked per listing type. An auction is a sale.
_SECTIONS = {"sale": ("vendita-case", "asta-case"), "rent": ("affitto-case",)}

_ENERGY_RE = re.compile(r"^[A-G]\d?\+*$")
_WALL_CLOCK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?")
# Image sizes per CDN "format": 0 original, 1 640x480, 2 640x427,
# 3 1280x960, 4 1920x1080. Stored: 1280x960 (the frontend swaps in 640x480
# for cards).
_IMAGE_FORMAT, _IMAGE_FALLBACK = 3, 1


def _city_slug(city: str) -> str:
    return re.sub(r"[\s']+", "-", city.strip().lower())


def _positive(value, cast=float):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _wall_clock(raw: str | None) -> str | None:
    """"2027-01-22T16:30:00.000+0000" → "2027-01-22T16:30".

    The offset is unreliable (the site shows 16:30 for this value, i.e.
    local time labelled UTC), so the local wall-clock time is kept as is."""
    m = _WALL_CLOCK_RE.match(raw or "")
    if not m:
        return None
    return f"{m.group(1)}T{m.group(2)}" if m.group(2) else m.group(1)


def _image_urls(entries: list | None, limit: int) -> list[str]:
    urls = []
    for entry in sorted(entries or [], key=lambda e: e.get("position") or 0):
        by_format = {i.get("format"): i.get("storagePath") for i in entry.get("images") or []}
        url = by_format.get(_IMAGE_FORMAT) or by_format.get(_IMAGE_FALLBACK)
        if url and url.startswith("http") and url not in urls:
            urls.append(url)
    return urls[:limit]


def _labels(soup: BeautifulSoup) -> dict[str, str]:
    """The detail's "Caratteristiche" grid: ``<p>Stato</p><span>Buone
    condizioni</span>`` pairs, keyed by lowercased label."""
    out: dict[str, str] = {}
    for p in soup.select("p.tw-text-12"):
        value = p.find_next_sibling()
        if value is not None and "tw-font-medium" in (value.get("class") or []):
            label = p.get_text(" ", strip=True).lower()
            text = value.get_text(" ", strip=True)
            if label and text:
                out.setdefault(label, text)
    return out


def _card_price(card: dict) -> float | None:
    """The card's price, on the same basis as the detail's. An auction
    card's ``price`` is the minimum offer (``priceFrom``); the listing's
    price is the base price, in ``priceSale`` — comparing the two would
    report a price drop at every scan."""
    if card.get("reservedPrice"):
        return None
    contract = card.get("contractType")
    if contract == "AUCTION":
        return _positive(card.get("auctionBasePrice")) or _positive(card.get("priceSale"))
    key = "priceRent" if contract == "RENT" else "priceSale"
    return _positive(card.get(key)) or _positive(card.get("price"))


def _flag(structured: bool, text: str, *keywords: str) -> bool | None:
    """Wikicasa's amenity booleans default to False, so only a ticked one is
    evidence; otherwise the description decides ("senza ascensore")."""
    if structured:
        return True
    return detect_feature(text, *keywords) if text else None


def _auction(re_: dict) -> dict | None:
    """The sale's data, for listings that are judicial auctions."""
    if not re_.get("auction"):
        return None
    number, year = re_.get("auctionProcedureNumber"), re_.get("auctionProcedureYear")
    info = {
        "date": _wall_clock(re_.get("auctionDate")),
        "base_price": _positive(re_.get("auctionBasePrice")) or _positive(re_.get("auctionStartingPrice")),
        "minimum_offer": _positive(re_.get("auctionMinimumOffer")),
        "minimum_raise": _positive(re_.get("auctionMinimumBid")),
        "offer_deadline": _wall_clock(re_.get("auctionSubmissionDeadline")),
        "court": re_.get("auctionCourtName") or None,
        "procedure": f"{number}/{year}" if number and year else None,
        "procedure_type": re_.get("auctionProcedureTypologyName") or None,
        "sale_mode": re_.get("auctionSaleModeName") or None,
        "pvp_url": re_.get("auctionPvpBookingLink") or None,
        "documents": [
            {"name": a.get("fileName") or "Documento", "url": a["url"]}
            for a in re_.get("attachments") or []
            if isinstance(a, dict) and str(a.get("url", "")).startswith("http")
        ],
    }
    return {k: v for k, v in info.items() if v not in (None, [])}


class WikicasaSpider(BaseSpider):
    portal_name = "wikicasa"
    base_url = "https://www.wikicasa.it"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._section = _SECTIONS["sale"][0]

    async def run(self, params: SearchParams):
        """Sales, then auctions: two result lists, one detail phase."""
        url_prices: dict[str, float | None] = {}
        walked_any = False
        for section in _SECTIONS.get(params.listing_type, _SECTIONS["sale"]):
            self._section = section
            found = await self.search_phase(params)
            if found is None:  # recorded as a failed search page
                continue
            walked_any = True
            for url, price in found.items():
                if url not in url_prices or url_prices[url] is None:
                    url_prices[url] = price
        if not walked_any:
            return
        async for item in self.detail_phase(url_prices, params):
            yield item

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        url = f"{self.base_url}/{self._section}/{_city_slug(params.city)}/"
        return f"{url}?p={page}" if page > 1 else url

    @staticmethod
    def _cards(html: str) -> tuple[list[dict], int]:
        store = pinia_store(nuxt_payload(html), "realEstateListingStoreId") or {}
        cards = [c for c in store.get("realEstateList") or [] if isinstance(c, dict)]
        return cards, _positive(store.get("listingCount"), int) or 0

    async def get_total_pages(self, html: str) -> int:
        _, count = self._cards(html)
        return max(1, math.ceil(count / PAGE_SIZE))

    async def parse_search_results(self, html: str) -> list[str]:
        return [url for url, _ in await self.parse_search_results_with_prices(html)]

    async def parse_search_results_with_prices(self, html: str) -> list[tuple[str, float | None]]:
        out = []
        cards, _ = self._cards(html)
        for card in cards:
            listing_id = card.get("realEstateID")
            if not listing_id:
                continue
            path = card.get("url") or f"/annuncio/{listing_id}"
            out.append((f"{self.base_url}{path}", _card_price(card)))
        return out

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        store = pinia_store(nuxt_payload(html), "realEstateDetailsStoreId") or {}
        re_ = store.get("realEstate")
        if not isinstance(re_, dict) or not re_.get("id"):
            # Served, but not a listing page: the layout changed, or the
            # listing was withdrawn and the site redirected elsewhere.
            raise ValueError("no realEstate in the Nuxt payload")

        labels = _labels(BeautifulSoup(html, "lxml"))
        description = re_.get("description") or re_.get("cleanDescription") or None
        text = description or ""
        title = store.get("title") or re_.get("typologyName") or "Annuncio Wikicasa"

        lat = lng = None
        # With the location hidden the payload holds the city's centre,
        # which would pile every such listing on one map pin.
        if re_.get("publishMap"):
            lat, lng = _positive(re_.get("latitude")), _positive(re_.get("longitude"))
            if lat is None or lng is None:
                lat = lng = None

        address = (re_.get("streetName") or re_.get("address") or "").strip() or None
        if not re_.get("publishAddress"):
            address = None

        energy = str(re_.get("energyClassType2015Name") or "").upper()
        expenses = _positive(re_.get("annualExpenses"))
        auction = _auction(re_)
        publication = re_.get("date") or None
        if auction and re_.get("auctionPvpPublicationDate"):
            publication = re_["auctionPvpPublicationDate"]

        garage = any(_positive(re_.get(k), int) for k in ("box", "doubleBox", "tripleBox", "numBox", "carSpot", "parking"))

        return ListingItem(
            source_portal="wikicasa",
            source_id=str(re_["id"]),
            source_url=f"{self.base_url}/annuncio/{re_['id']}",
            title=title,
            description=description,
            price=None if re_.get("reservedPrice") else (
                (auction or {}).get("base_price") or _positive(re_.get("price"))
            ),
            area_sqm=_positive(re_.get("sqM")),
            rooms=_positive(re_.get("rooms"), int),
            bedrooms=_positive(re_.get("bedrooms"), int),
            bathrooms=_positive(re_.get("bathrooms"), int),
            floor=str(re_["floor"]).strip() if re_.get("floor") not in (None, "") else None,
            total_floors=_positive(re_.get("buildingFloors"), int),
            address=address,
            city=(re_.get("cityName") or "").strip().lower(),
            zone=re_.get("zoneName") or re_.get("districtName") or None,
            province=(store.get("place") or {}).get("provinceAcronym") or None,
            lat=lat,
            lng=lng,
            property_type=map_property_type(re_.get("typologyName") or title),
            listing_type="rent" if re_.get("rent") and not re_.get("sale") else "sale",
            images=_image_urls(re_.get("reImages"), 30),
            floor_plans=_image_urls(re_.get("rePlanimetries"), 10),
            energy_class=energy if _ENERGY_RE.match(energy) else None,
            condition=map_condition(labels.get("stato")),
            heating=labels.get("riscaldamento"),
            has_elevator=_flag(bool(re_.get("lift")), text, "ascensore"),
            has_balcony=_flag(bool(re_.get("hasBalconies") or _positive(re_.get("balconies"), int)), text, "balcon"),
            has_terrace=_flag(False, text, "terrazz"),
            has_garage=_flag(garage, text, "garage", "box auto", "posto auto"),
            has_garden=_flag(bool(re_.get("garden") or re_.get("gardenPublic")), text, "giardin"),
            # Wikicasa states the yearly figure; the app's field is monthly.
            condominium_fees=round(expenses / 12, 2) if expenses else None,
            year_built=_year(re_.get("buildingYear")),
            publication_date=str(publication)[:10] if publication else None,
            is_auction=bool(re_.get("auction")),
            auction=auction,
            raw_data={"reference": re_.get("reference"), "agency": re_.get("agencyName")},
        )


def _year(raw) -> int | None:
    year = _positive(raw, int)
    if year and 1500 <= year <= datetime.now(timezone.utc).year + 5:
        return year
    return None
