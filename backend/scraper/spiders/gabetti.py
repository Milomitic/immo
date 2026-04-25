"""
Gabetti.it spider.

Gabetti is a Next.js 15 site using React Server Components. Detail pages
ship their data through `self.__next_f.push([1, "..."])` RSC chunks; one
of those chunks contains a serialized `property` object with every field
(price, lat/lng, features, floor, energy_class, ...). Search listings use
plain server-rendered `<a href="/vendita/{city}/{type}/{id}">` anchors.

Gabetti doesn't expose any publication date in the RSC payload or DOM.
As a proxy we send a HEAD request to the first listing image (hosted on
``api.gabettigroup.com``) and use its ``Last-Modified`` header — the CDN
timestamp reliably reflects when the agent uploaded the photo, which
coincides with listing creation.

Search URL patterns:
  /casa/vendita/{city}   (redirects to /vendita/{city}?tipoDestinazioneUso=1)
  /casa/affitto/{city}   (redirects to /affitto/{city}?tipoDestinazioneUso=1)
Pagination: ?page=N
"""

import json
import re
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import map_property_type


# Matches href="/vendita/{city}/{type}/{id}" and the affitto variant.
_LISTING_HREF_RE = re.compile(
    r'href="(/(?:vendita|affitto)/[a-z0-9\-]+/[a-z0-9\-]+/\d+)(?:[?#][^"]*)?"'
)

# RSC push format: self.__next_f.push([1,"<JS-encoded string>"])
_RSC_PUSH_RE = re.compile(
    r'self\.__next_f\.push\(\[\d+,"(.+?)"\]\)', re.DOTALL
)


def _extract_property_json(html: str) -> dict | None:
    """Walk the Next.js RSC chunks, find the one that carries the
    `property` object, and return it as a dict.

    The RSC string is JS-encoded (every `"` inside is `\"`), so we
    un-escape by wrapping it in a pair of real quotes and running it back
    through `json.loads`. Only then can we search the resulting text for
    the `"property":{...}` object.
    """
    for raw in _RSC_PUSH_RE.findall(html):
        # In raw the `"` chars are still escaped as `\"`, so we compare
        # against the escaped form.
        if '\\"price\\":' not in raw or '\\"lat\\":' not in raw:
            continue
        try:
            unescaped = json.loads(f'"{raw}"')
        except (json.JSONDecodeError, ValueError):
            continue
        obj = _extract_balanced_object(unescaped, '"property":')
        if obj and obj.get("id"):
            return obj
    return None


def _extract_balanced_object(text: str, marker: str) -> dict | None:
    """Find `marker` in `text` and return the JSON object that directly
    follows it. Walks the string counting braces so it doesn't trip over
    nested objects."""
    idx = text.find(marker)
    if idx < 0:
        return None
    start = text.find("{", idx + len(marker))
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return BeautifulSoup(text, "lxml").get_text(" ", strip=True) or None


def _clean_energy_class(raw) -> str | None:
    """Gabetti writes "N.V." when the class is unknown; strip that to None."""
    if not raw:
        return None
    s = str(raw).strip().upper()
    if not s or s in ("N.V.", "NV", "N.D.", "ND", "-"):
        return None
    m = re.match(r"([A-G]\d?\+?)", s)
    return m.group(1) if m else None


def _split_city(raw: str | None) -> tuple[str, str | None]:
    """Gabetti writes city as "Bari (BA)" — peel off the 2-letter province."""
    if not raw:
        return "unknown", None
    m = re.match(r"(.+?)\s*\(([A-Z]{2})\)\s*$", raw)
    if m:
        return m.group(1).strip().lower(), m.group(2)
    return raw.strip().lower(), None


class GabettiSpider(BaseSpider):
    portal_name = "gabetti"
    base_url = "https://www.gabetti.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        contract = "vendita" if params.listing_type == "sale" else "affitto"
        city_slug = params.city.lower().replace(" ", "-")
        url = f"{self.base_url}/casa/{contract}/{city_slug}"
        if page > 1:
            url += f"?page={page}"
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for m in _LISTING_HREF_RE.finditer(html):
            path = m.group(1)
            url = self.base_url + path
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    async def get_total_pages(self, html: str) -> int:
        """Gabetti prints "Pagina 1 di N" in the pagination bar. We also
        collect any ?page= references as a fallback."""
        m = re.search(r"Pagina\s+\d+\s+di\s+(\d+)", html)
        if m:
            return int(m.group(1))
        pages = [int(p) for p in re.findall(r"[?&]page=(\d+)", html)]
        return max(pages) if pages else 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        prop = _extract_property_json(html)
        if not prop:
            return None

        source_id = str(prop.get("id") or "").strip()
        if not source_id:
            m = re.search(r"/(\d{4,})(?:[/?]|$)", url)
            if not m:
                return None
            source_id = m.group(1)

        category = (prop.get("category") or "").lower()
        listing_type = "rent" if "affitto" in category or "locazione" in category else "sale"

        type_label = prop.get("type") or prop.get("typeSlug") or ""
        property_type = map_property_type(type_label)

        price = prop.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None

        area_sqm = prop.get("squareMeters")
        try:
            area_sqm = float(area_sqm) if area_sqm is not None else None
        except (TypeError, ValueError):
            area_sqm = None

        features = prop.get("features") or {}
        rooms = features.get("rooms") or prop.get("rooms")
        bathrooms = features.get("bathrooms") or prop.get("bathrooms")
        bedrooms = features.get("bedrooms")
        floor = features.get("floor") or None
        year_built = features.get("year_of_construction") or None
        if not isinstance(year_built, int):
            try:
                year_built = int(year_built) if year_built is not None else None
            except (TypeError, ValueError):
                year_built = None

        balconies = features.get("balconies") or 0
        terraces = features.get("terraces") or 0
        garages = (features.get("garage") or 0) + (features.get("parking_spaces") or 0)
        garden = features.get("garden")

        has_balcony = bool(balconies) if features.get("balconies") is not None else None
        has_terrace = bool(terraces) if features.get("terraces") is not None else None
        has_garage = bool(garages) if (features.get("garage") is not None or features.get("parking_spaces") is not None) else None
        has_garden = None
        if garden is not None and garden != "":
            has_garden = bool(garden)

        energy_class = _clean_energy_class(features.get("energy_class"))
        condition = features.get("property_condition") or None
        heating = features.get("heating") or None
        condo_fees = features.get("condominium_fees")
        try:
            condo_fees = float(condo_fees) if condo_fees is not None else None
        except (TypeError, ValueError):
            condo_fees = None

        city, province = _split_city(prop.get("city"))
        address = prop.get("address") or None

        lat = prop.get("lat")
        lng = prop.get("lon")
        try:
            lat = float(lat) if lat is not None else None
        except (TypeError, ValueError):
            lat = None
        try:
            lng = float(lng) if lng is not None else None
        except (TypeError, ValueError):
            lng = None

        # Description sits in a DOM section because the RSC payload uses a ref.
        soup = BeautifulSoup(html, "lxml")
        desc_el = soup.find(id="description")
        description = None
        if desc_el:
            desc_text = desc_el.get_text(" ", strip=True)
            # Strip the leading "Descrizione" heading if present
            description = re.sub(r"^Descrizione\s*", "", desc_text)[:4000] or None

        # Images are usually full URLs already.
        images: list[str] = []
        for img in (prop.get("images") or []):
            if isinstance(img, str) and img.startswith("http"):
                images.append(img)

        # Publication date: HEAD the first image for its Last-Modified header.
        publication_date = await self._pub_date_from_image(images[0] if images else None)

        # Title: pick a readable summary.
        title_bits = [type_label, address or "", city.title() if city != "unknown" else ""]
        title = " - ".join([b for b in title_bits if b]) or f"Annuncio gabetti {source_id}"

        return ListingItem(
            source_portal=self.portal_name,
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=int(rooms) if isinstance(rooms, (int, float)) else None,
            bedrooms=int(bedrooms) if isinstance(bedrooms, (int, float)) else None,
            bathrooms=int(bathrooms) if isinstance(bathrooms, (int, float)) else None,
            floor=floor,
            address=address,
            city=city,
            zone=None,
            province=province,
            lat=lat,
            lng=lng,
            property_type=property_type,
            listing_type=listing_type,
            images=images,
            energy_class=energy_class,
            condition=condition,
            heating=heating,
            has_elevator=None,  # not in payload
            has_balcony=has_balcony,
            has_terrace=has_terrace,
            has_garage=has_garage,
            has_garden=has_garden,
            condominium_fees=condo_fees,
            year_built=year_built,
            publication_date=publication_date,
            raw_data={"agency_id": prop.get("agencyId")},
        )

    async def _pub_date_from_image(self, image_url: str | None) -> str | None:
        """HEAD the first listing image on gabetti's CDN and return the
        ``Last-Modified`` date as ISO 8601. The CDN timestamp reflects when
        the agent uploaded the photo — a reliable proxy for listing creation.
        """
        if not image_url:
            return None
        try:
            client = await self._get_client()
            resp = await client.head(image_url, timeout=10)
            last_mod = resp.headers.get("last-modified")
            if not last_mod:
                return None
            dt = parsedate_to_datetime(last_mod)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None
