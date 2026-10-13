"""
Tecnocasa.it spider.

Tecnocasa is a Vue.js SSR site. The search list page embeds each listing as a
Vue component with an `:estate="{...}"` prop whose JSON contains the full
listing — including the canonical `detail_url`. Detail pages repeat the same
prop with *more* fields (features, energy_data, lat/lng, last_published_at),
so we just parse that JSON blob instead of screen-scraping the rendered DOM.

Search URL patterns:
  Sale:  /annunci/immobili/{region}/{province}.html[/pag-N]
  Rent:  /affitto/immobili/{region}/{province}.html[/pag-N]

Tecnocasa groups listings by Italian region + province slug, so the spider
needs a city -> (region, province) mapping for each supported city.
"""

import html as html_lib
import json
import re

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import map_property_type, parse_int

# City slug -> (region slug, province slug). Tecnocasa's URL structure
# requires the Italian region in the path, which isn't derivable from the
# city alone. Bari is the project's default; the rest are the main Italian
# metros. Unknown cities fall back to the city-as-province heuristic.
_CITY_TO_REGION: dict[str, tuple[str, str]] = {
    "bari": ("puglia", "bari"),
    "milano": ("lombardia", "milano"),
    "roma": ("lazio", "roma"),
    "torino": ("piemonte", "torino"),
    "napoli": ("campania", "napoli"),
    "firenze": ("toscana", "firenze"),
    "bologna": ("emilia-romagna", "bologna"),
    "genova": ("liguria", "genova"),
    "palermo": ("sicilia", "palermo"),
    "catania": ("sicilia", "catania"),
    "messina": ("sicilia", "messina"),
    "verona": ("veneto", "verona"),
    "venezia": ("veneto", "venezia"),
    "padova": ("veneto", "padova"),
    "trieste": ("friuli-venezia-giulia", "trieste"),
    "brescia": ("lombardia", "brescia"),
    "bergamo": ("lombardia", "bergamo"),
    "modena": ("emilia-romagna", "modena"),
    "parma": ("emilia-romagna", "parma"),
    "reggio-emilia": ("emilia-romagna", "reggio-emilia"),
    "cagliari": ("sardegna", "cagliari"),
    "ancona": ("marche", "ancona"),
    "perugia": ("umbria", "perugia"),
    "pescara": ("abruzzo", "pescara"),
    "lecce": ("puglia", "lecce"),
    "taranto": ("puglia", "taranto"),
    "foggia": ("puglia", "foggia"),
    "brindisi": ("puglia", "brindisi"),
}


# Match `detail_url&quot;:&quot;https:\/\/www.tecnocasa.it\/...&quot;`.
# The JSON-encoded `\/` remains in the attribute value as a literal `\/`;
# only the `"` chars get HTML-escaped to `&quot;`.
_DETAIL_URL_RE = re.compile(
    r'detail_url&quot;:&quot;(https:\\/\\/www\.tecnocasa\.it[^&]+?)&quot;'
)

# `:estate="..."` prop on the detail page (and on cards within the list page).
# We match a single balanced-ish JSON object: non-greedy up to the closing
# quote. Vue SSR always emits this as a double-quoted attribute, and the
# inner JSON has no literal `"` (all escaped to `&quot;`), so the pattern is
# unambiguous.
_ESTATE_PROP_RE = re.compile(r':estate="(\{&quot;.+?\})"', re.DOTALL)


def _unescape_detail_url(raw: str) -> str:
    return raw.replace("\\/", "/")


def _parse_estate_json(html: str) -> dict | None:
    """Return the first `:estate` Vue prop JSON found on the page."""
    m = _ESTATE_PROP_RE.search(html)
    if not m:
        return None
    try:
        unesc = html_lib.unescape(m.group(1)).replace("\\/", "/")
        return json.loads(unesc)
    except (json.JSONDecodeError, ValueError):
        return None


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return BeautifulSoup(text, "lxml").get_text(" ", strip=True) or None


def _yesno(val) -> bool | None:
    """Map tecnocasa yes/no-ish fields (Sì/No/None) to bool | None."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if not s or s in ("no", "assente", "-"):
        return False
    if s in ("s\u00ec", "si", "sì", "presente", "autonomo", "centralizzato"):
        return True
    return None


def _parse_last_published(raw: str | None) -> str | None:
    """Parse "2025-09-02 17:39:33" into ISO 8601 date."""
    if not raw:
        return None
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


class TecnocasaSpider(BaseSpider):
    portal_name = "tecnocasa"
    base_url = "https://www.tecnocasa.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        city_slug = params.city.lower().replace(" ", "-")
        region, province = _CITY_TO_REGION.get(
            city_slug, (city_slug, city_slug)  # best-effort fallback
        )
        contract_root = "annunci" if params.listing_type == "sale" else "affitto"
        url = f"{self.base_url}/{contract_root}/immobili/{region}/{province}.html"
        if page > 1:
            url += f"/pag-{page}"
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for m in _DETAIL_URL_RE.finditer(html):
            url = _unescape_detail_url(m.group(1))
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    async def get_total_pages(self, html: str) -> int:
        """Tecnocasa's pagination bar exposes all page numbers as /pag-N
        fragments — grab the highest one."""
        pages = [int(p) for p in re.findall(r"/pag-(\d+)", html)]
        return max(pages) if pages else 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        data = _parse_estate_json(html)
        if not data:
            return None

        # --- identity
        source_id = str(data.get("id") or "").strip()
        if not source_id:
            m = re.search(r"/(\d{6,})\.html", url)
            if m:
                source_id = m.group(1)
        if not source_id:
            return None

        # --- contract / property type
        contract = data.get("contract") or {}
        contract_slug = (contract.get("slug_estate") or contract.get("title") or "").lower()
        listing_type = "rent" if "affitto" in contract_slug or "locazione" in contract_slug else "sale"

        title = data.get("title") or ""
        subtitle = data.get("subtitle") or ""
        property_type = map_property_type(title)

        # --- location
        city_obj = data.get("city") or {}
        city = (city_obj.get("title") or city_obj.get("slug") or "unknown").lower()

        district = data.get("district") or {}
        zone = district.get("title") or None

        address = data.get("address") or None
        province = None  # tecnocasa omits the 2-letter province on the estate payload

        lat = data.get("latitude")
        lng = data.get("longitude")
        try:
            lat = float(lat) if lat is not None else None
        except (TypeError, ValueError):
            lat = None
        try:
            lng = float(lng) if lng is not None else None
        except (TypeError, ValueError):
            lng = None

        # --- price / surface / rooms
        costs = data.get("costs") or {}
        price = costs.get("numeric_price") or data.get("numeric_price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None

        area_raw = data.get("numeric_surface")
        try:
            area_sqm = float(area_raw) if area_raw is not None else None
        except (TypeError, ValueError):
            area_sqm = None

        rooms = parse_int(data.get("rooms"))
        bathrooms = parse_int(data.get("bathrooms"))

        # --- features block
        features = data.get("features") or {}
        bedrooms = features.get("bedrooms")
        if bedrooms is None:
            bedrooms = parse_int(data.get("bedrooms_small"))
        floor = features.get("floor") or None
        year_built = features.get("build_year") or None
        if not isinstance(year_built, int):
            year_built = parse_int(year_built)

        has_elevator = _yesno(features.get("elevator_immo"))
        has_balcony = (features.get("balconies") or 0) > 0 if isinstance(features.get("balconies"), int) else None
        has_terrace = (features.get("terraces") or 0) > 0 if isinstance(features.get("terraces"), int) else None
        has_garage = (features.get("box") or 0) > 0 or (features.get("car_places") or 0) > 0
        if not has_garage and features.get("box") is None and features.get("car_places") is None:
            has_garage = None
        garden_val = features.get("garden")
        if garden_val is None or garden_val == "":
            has_garden = None
        else:
            has_garden = bool(garden_val)

        # --- energy class
        energy = data.get("energy_data") or {}
        energy_class_raw = (energy.get("class") or "").strip()
        energy_class = energy_class_raw.upper() if energy_class_raw else None

        # --- description
        description = _strip_html(data.get("description"))
        if description:
            description = description[:4000]

        # --- images
        images: list[str] = []
        media = data.get("media") or {}
        for img in (media.get("images") or []):
            if not isinstance(img, dict):
                continue
            urls_obj = img.get("url") or img
            if isinstance(urls_obj, dict):
                pick = (
                    urls_obj.get("detail")
                    or urls_obj.get("gallery")
                    or urls_obj.get("gallery_media")
                    or urls_obj.get("card")
                )
                if isinstance(pick, str) and pick.startswith("http"):
                    images.append(pick)

        # --- publication date (the whole reason we rewrote this spider)
        publication_date = _parse_last_published(data.get("last_published_at"))

        # Assemble a readable title
        full_title = title
        if subtitle:
            full_title = f"{title} - {subtitle}" if title else subtitle

        return ListingItem(
            source_portal=self.portal_name,
            source_id=source_id,
            source_url=url,
            title=full_title or f"Annuncio tecnocasa {source_id}",
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=rooms,
            bedrooms=bedrooms if isinstance(bedrooms, int) else None,
            bathrooms=bathrooms,
            floor=floor,
            address=address,
            city=city or "unknown",
            zone=zone,
            province=province,
            lat=lat,
            lng=lng,
            property_type=property_type,
            listing_type=listing_type,
            images=images,
            energy_class=energy_class,
            has_elevator=has_elevator,
            has_balcony=has_balcony,
            has_terrace=has_terrace,
            has_garage=has_garage,
            has_garden=has_garden,
            year_built=year_built if isinstance(year_built, int) else None,
            publication_date=publication_date,
            raw_data={"subtitle": subtitle, "district": district.get("title")},
        )
