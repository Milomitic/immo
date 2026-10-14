"""
Bakeca.it spider — a classifieds site where agencies and private sellers
republish their listings.

* Search: ``https://{city}.bakeca.it/annunci/{vendita|affitto}-case/page/N/``,
  25 cards per page, each with schema.org JSON-LD (url, price, town,
  coordinates). The subdomain covers the whole province: cards of other
  towns are skipped.
* Detail: the JSON-LD has the whole description, every photo, the
  coordinates and a few ``amenityFeature`` values (typology, m², energy
  class); the page's "meta" blocks add the neighbourhood. Amenities come
  from the description, as for the other portals without structured ones.
"""

import html as html_lib
import json
import math
import re

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import detect_feature, map_condition, map_property_type

PAGE_SIZE = 25
_ID_RE = re.compile(r"-([a-z0-9]{10,})/?(?:[?#].*)?$")
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_COUNT_RE = re.compile(r"(\d[\d.]*)\s+annunci", re.IGNORECASE)
_ENERGY_RE = re.compile(r"^([A-G]\d?\+*)")
_ROOMS_RE = re.compile(r"con (\d+) local", re.IGNORECASE)
_AREA_RE = re.compile(r"di (\d+(?:[.,]\d+)?) m", re.IGNORECASE)
_ROOMS_BY_TYPOLOGY = {"monolocale": 1, "bilocale": 2, "trilocale": 3, "quadrilocale": 4, "pentalocale": 5}


def _city_slug(city: str) -> str:
    return re.sub(r"[\s']+", "-", city.strip().lower())


def _text(value) -> str:
    """JSON-LD strings come HTML-escaped ("m&sup2;", "citt&agrave;")."""
    return html_lib.unescape(str(value or "")).strip()


def _residences(page: str) -> list[dict]:
    out = []
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        types = data.get("@type") if isinstance(data, dict) else None
        if isinstance(types, list) and "SingleFamilyResidence" in types:
            out.append(data)
    return out


def _price(ld: dict) -> float | None:
    try:
        price = float((ld.get("offers") or {}).get("price"))
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _meta(soup: BeautifulSoup) -> dict[str, str]:
    """The detail's "meta" blocks: ``<span class="meta-label">Quartiere:</span> Libertà``."""
    out: dict[str, str] = {}
    for block in soup.select(".meta-block"):
        label = block.select_one(".meta-label")
        if not label:
            continue
        key = label.get_text(" ", strip=True).rstrip(":").strip().lower()
        label.extract()
        value = block.get_text(" ", strip=True)
        if key and value:
            out.setdefault(key, value)
    return out


class BakecaSpider(BaseSpider):
    portal_name = "bakeca"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._city = ""
        self._contract = "vendita"

    @property
    def base_url(self) -> str:  # one subdomain per province
        return f"https://{_city_slug(self._city or 'bari')}.bakeca.it"

    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        m = _ID_RE.search(url)
        return m.group(1) if m else None

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        self._city = params.city
        self._contract = "affitto" if params.listing_type == "rent" else "vendita"
        url = f"{self.base_url}/annunci/{self._contract}-case/"
        return f"{url}page/{page}/" if page > 1 else url

    async def get_total_pages(self, html: str) -> int:
        m = _COUNT_RE.search(BeautifulSoup(html, "lxml").get_text(" "))
        if m:
            return max(1, math.ceil(int(m.group(1).replace(".", "")) / PAGE_SIZE))
        pages = [int(p) for p in re.findall(r"/page/(\d+)/", html)]
        return max(pages, default=1)

    async def parse_search_results(self, html: str) -> list[str]:
        return [url for url, _ in await self.parse_search_results_with_prices(html)]

    async def parse_search_results_with_prices(self, html: str) -> list[tuple[str, float | None]]:
        out = []
        for ld in _residences(html):
            town = _text((ld.get("address") or {}).get("addressLocality")).lower()
            if self._city and town and town != self._city.strip().lower():
                continue  # the province's other towns
            url = str(ld.get("url") or "").split("?")[0]
            if url and self._extract_source_id_from_url(url):
                out.append((url, _price(ld)))
        return out

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        lds = _residences(html)
        if not lds:
            raise ValueError("no listing JSON-LD on the page")
        ld = lds[0]
        soup = BeautifulSoup(html, "lxml")
        meta = _meta(soup)
        features = {_text(f.get("name")).lower(): f.get("value")
                    for f in ld.get("amenityFeature") or [] if isinstance(f, dict)}

        title = _text(ld.get("name")) or "Annuncio Bakeca"
        description = _text(ld.get("description")) or None
        text = description or ""
        typology = _text(features.get("tipo immobile"))

        rooms = _ROOMS_BY_TYPOLOGY.get(typology.lower())
        if rooms is None and (m := _ROOMS_RE.search(title)):
            rooms = int(m.group(1))
        area = None
        try:
            area = float(features.get("metri quadri (m2)") or 0) or None
        except (TypeError, ValueError):
            area = None
        if area is None and (m := _AREA_RE.search(title)):
            area = float(m.group(1).replace(",", "."))

        energy_match = _ENERGY_RE.match(str(features.get("classe energetica") or "").upper())
        geo = ld.get("geo") or {}
        try:
            lat, lng = float(geo["latitude"]), float(geo["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lng = None

        photos = []
        for photo in ld.get("photo") or []:
            src = photo.get("contentUrl") if isinstance(photo, dict) else None
            if src and src.startswith("http") and src not in photos:
                photos.append(src)
        if not photos and str(ld.get("image") or "").startswith("http"):
            photos.append(ld["image"])

        seller = ((ld.get("offers") or {}).get("seller") or {}).get("name")
        return ListingItem(
            source_portal="bakeca",
            source_id=self._extract_source_id_from_url(url) or str(ld.get("productID") or ""),
            source_url=url.split("?")[0],
            title=title,
            description=description,
            price=_price(ld),
            area_sqm=area,
            rooms=rooms,
            city=(_text((ld.get("address") or {}).get("addressLocality")) or self._city).lower(),
            # long lists come cut short: "Picone, Carrassi, San Pasquale …"
            zone=(meta.get("quartiere") or "").rstrip(" …").rstrip(" .,") or None,
            lat=lat,
            lng=lng,
            property_type=map_property_type(typology or title),
            listing_type="rent" if "/affitto-" in url else "sale",
            images=photos[:30],
            energy_class=energy_match.group(1) if energy_match else None,
            condition=map_condition(meta.get("stato") or meta.get("condizioni")),
            has_elevator=detect_feature(text, "ascensore"),
            has_balcony=detect_feature(text, "balcon"),
            has_terrace=detect_feature(text, "terrazz"),
            has_garage=detect_feature(text, "garage", "box auto", "posto auto"),
            has_garden=detect_feature(text, "giardin"),
            raw_data={"advertiser": seller} if seller else {},
        )
