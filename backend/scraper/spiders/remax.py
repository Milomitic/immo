"""
Remax.it spider.

remax.it moved from Nuxt to the Next.js App Router in 2026. Both page kinds
now ship structured data, so nothing is scraped from markup:

* Search: ``/{vendita|affitto}-case/{city}?page=N``, 12 cards per page.
  Listing URLs come from the schema.org ``ItemList`` (JSON-LD); each card's
  ``code`` and ``price``, plus ``{"currentPage":..,"totalPages":..}``, from
  the RSC flight payload (see ``scraper.utils.rsc``).
* Detail: agency-subdomain URLs ending in the listing code, e.g.
  ``https://oltre.remax.it/vendita-villa-o-villino/bari/<zona>-36681014-42``.
  The flight carries a ``"property":{...}`` object with structured
  amenities, energy class, coordinates, ``publishedAt`` and photos flagged
  ``isFloorPlan``; the description is a separate text row (``"$NN"``).

The code ("36681014-42") has the same shape the old site used as source_id,
so listings recorded before the redesign keep their identity.
"""

import json
import math
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import (
    clamp_italy_coords,
    clamp_publication_date,
    detect_feature,
    map_condition,
    map_property_type,
)
from scraper.utils.rsc import flight_payload, json_values_after, resolve_text

PAGE_SIZE = 12

_CODE_RE = re.compile(r"-(\d+-\d+)/?(?:[?#].*)?$")
_PAGES_RE = re.compile(r'"currentPage":\d+,"totalPages":(\d+)')
_COUNT_RE = re.compile(r"(\d[\d.]*)\s+(?:case|immobili)\s+in\s+(?:vendita|affitto)", re.IGNORECASE)
_ENERGY_RE = re.compile(r"^[A-G]\d?\+*$")

# remax floor keys → the floor filter's vocabulary (digits, T, R, S).
_FLOORS = {
    "piano_terra": "T",
    "piano_rialzato": "R",
    "seminterrato": "S",
    "interrato": "S",
    "controterra": "S",
    "su_due_livelli": "Più livelli",
    "multipiano": "Più livelli",
    "ultimo": "Ultimo",
    "attico": "Attico",
}


def _code_from_url(url: str) -> str | None:
    m = _CODE_RE.search(url)
    return m.group(1) if m else None


def _ld_blocks(soup: BeautifulSoup, type_name: str) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == type_name:
            blocks.append(data)
    return blocks


def _price(prop: dict) -> float | None:
    if prop.get("isConfidential"):  # "Trattativa riservata"
        return None
    price = prop.get("price")
    return float(price) if isinstance(price, (int, float)) and price > 0 else None


def _positive(value, cast=float):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _any_flag(*values: bool | None) -> bool | None:
    """Merge structured booleans: any True wins, then any explicit False."""
    if any(v is True for v in values):
        return True
    if any(v is False for v in values):
        return False
    return None


def _flag(structured: bool | None, text: str, *keywords: str) -> bool | None:
    """The structured checkbox decides when ticked; otherwise the description
    can still reveal an amenity the agent didn't tick, or deny it
    ("senza ascensore")."""
    if structured is True:
        return True
    from_text = detect_feature(text, *keywords) if text else None
    return from_text if from_text is not None else structured


def _floor(raw) -> str | None:
    if raw is None or raw == "":
        return None
    raw = str(raw)
    return _FLOORS.get(raw, raw.replace("_", " "))


def _year(raw) -> int | None:
    year = _positive(raw, int)
    if year and 1500 <= year <= datetime.now(timezone.utc).year + 5:
        return year
    return None


def _html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    return BeautifulSoup(html, "lxml").get_text("\n", strip=True) or None


class RemaxSpider(BaseSpider):
    portal_name = "remax"
    base_url = "https://www.remax.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        contract = "affitto" if params.listing_type == "rent" else "vendita"
        city = re.sub(r"[^a-z0-9]+", "-", params.city.lower()).strip("-")
        url = f"{self.base_url}/{contract}-case/{city}"
        return f"{url}?page={page}" if page > 1 else url

    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        return _code_from_url(url)

    async def parse_search_results(self, html: str) -> list[str]:
        return [url for url, _ in await self.parse_search_results_with_prices(html)]

    async def parse_search_results_with_prices(self, html: str) -> list[tuple[str, float | None]]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        seen: set[str] = set()
        for block in _ld_blocks(soup, "ItemList"):
            for element in block.get("itemListElement") or []:
                url = element.get("url") if isinstance(element, dict) else None
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)

        cards: dict[str, dict] = {}
        for prop in json_values_after(flight_payload(html), "property"):
            if isinstance(prop, dict) and prop.get("code"):
                cards.setdefault(prop["code"], prop)

        results = []
        for url in urls:
            card = cards.get(_code_from_url(url) or "")
            results.append((url, _price(card) if card else None))
        return results

    async def get_total_pages(self, html: str) -> int:
        m = _PAGES_RE.search(flight_payload(html))
        if m:
            return max(1, int(m.group(1)))
        # Fallback: "437 case in vendita a Bari" in the meta description.
        meta = BeautifulSoup(html, "lxml").find("meta", attrs={"name": "description"})
        m = _COUNT_RE.search(meta.get("content", "") if meta else "")
        if m:
            return max(1, math.ceil(int(m.group(1).replace(".", "")) / PAGE_SIZE))
        return 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        flight = flight_payload(html)
        code = _code_from_url(url)
        candidates = [
            p for p in json_values_after(flight, "property") if isinstance(p, dict) and p.get("code")
        ]
        # Detail pages may also embed cards of similar listings: prefer the
        # code from the URL, then the only object carrying a photo gallery.
        prop = next((p for p in candidates if p["code"] == code), None) or next(
            (p for p in candidates if "photos" in p), None
        )
        if prop is None:
            raise ValueError("remax: property payload not found")

        soup = BeautifulSoup(html, "lxml")
        ld = next(iter(_ld_blocks(soup, "RealEstateListing")), {})

        description = (
            _html_to_text(resolve_text(flight, prop.get("description")))
            or ld.get("description")
            or prop.get("shortDescription")
            or None
        )
        if description:
            description = description[:4000]
        text = description or ""

        photos = sorted(
            (p for p in prop.get("photos") or [] if isinstance(p, dict) and p.get("url")),
            key=lambda p: p.get("order") or 0,
        )
        images = [p["url"] for p in photos if not p.get("isFloorPlan")]
        floor_plans = [p["url"] for p in photos if p.get("isFloorPlan")]
        if not images and prop.get("mainPhotoUrl"):
            images = [prop["mainPhotoUrl"]]

        macro = (prop.get("macroCategory") or "").lower()
        if macro in ("commerciale", "industriale"):
            property_type = "commercial"
        elif macro == "terreni":
            property_type = "land"
        else:
            property_type = self._remax_property_type((prop.get("propertyType") or "").replace("_", " "))

        lat, lng = clamp_italy_coords(prop.get("latitude"), prop.get("longitude"))
        energy_class = (prop.get("energyClass") or "").upper()
        heating = prop.get("heating")
        page_title = soup.title.get_text(strip=True).split(" | ")[0] if soup.title else ""

        return ListingItem(
            source_portal=self.portal_name,
            source_id=prop["code"],
            source_url=url,
            title=ld.get("name") or page_title or f"Annuncio remax {prop['code']}",
            description=description,
            price=_price(prop),
            area_sqm=_positive(prop.get("totalArea")),
            rooms=_positive(prop.get("rooms"), int),
            bedrooms=_positive(prop.get("bedrooms"), int),
            bathrooms=_positive(prop.get("bathrooms"), int),
            floor=_floor(prop.get("floor")),
            total_floors=_positive(prop.get("totalFloors"), int),
            address=prop.get("address") or (ld.get("address") or {}).get("streetAddress"),
            city=(prop.get("city") or "").strip().lower() or "unknown",
            zone=prop.get("neighborhood") or prop.get("quadrantName"),
            province=prop.get("province"),
            lat=lat,
            lng=lng,
            property_type=property_type,
            listing_type="rent" if prop.get("contractType") == "affitto" else "sale",
            images=images,
            floor_plans=floor_plans,
            energy_class=energy_class if _ENERGY_RE.match(energy_class) else None,
            condition=map_condition((prop.get("conservationState") or "").replace("_", " ")),
            heating=heating.replace("_", " ") if heating else None,
            has_elevator=_flag(prop.get("hasElevator"), text, "ascensore"),
            has_balcony=_flag(prop.get("hasBalcony"), text, "balcon"),
            has_terrace=_flag(prop.get("hasTerrace"), text, "terrazz"),
            has_garage=_flag(
                _any_flag(prop.get("hasGarage"), prop.get("hasBox"), prop.get("hasParking")),
                text, "garage", "box auto", "posto auto",
            ),
            has_garden=_flag(prop.get("hasGarden"), text, "giardin"),
            condominium_fees=_positive(prop.get("condominiumFees")),
            year_built=_year(prop.get("constructionYear")),
            publication_date=clamp_publication_date(prop.get("publishedAt")),
            raw_data={
                "remax_id": prop.get("id"),
                "gestim_id": prop.get("gestimId"),
                "agency": prop.get("agencyName"),
            },
        )

    @staticmethod
    def _remax_property_type(raw: str) -> str:
        """Map remax's property type label to ListingItem.property_type.

        Remax sells more than apartments — hotels, land, commercial, etc. —
        so we widen the mapping beyond the shared helper.
        """
        if not raw:
            return "apartment"
        lower = raw.lower()
        if "agriturismo" in lower or "albergo" in lower or "hotel" in lower or "b&b" in lower:
            return "commercial"
        if "ufficio" in lower or "negozio" in lower or "capannone" in lower or "magazzino" in lower:
            return "commercial"
        if "terreno" in lower:
            return "land"
        if "villa" in lower:
            return "villa"
        if "rustico" in lower or "casale" in lower or "casa" in lower or "villino" in lower:
            return "house"
        if "loft" in lower:
            return "loft"
        if "monolocale" in lower:
            return "studio"
        return map_property_type(lower)
