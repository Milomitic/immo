"""
Remax.it spider.

Remax is a Nuxt.js site. Detail pages render a fixed "unit-overview" block
server-side with all the headline fields (price, property type, address,
area, rooms) plus a small grid of "unit-feature" rows (bathrooms, bedrooms,
energy class). Photos are lazy-loaded via JS, so we fall back to og:image
for the cover shot.

Search URL pattern: /trova/ricerca/{Vendita|Affitto}/{City}?page=N
"""

import base64
import re

from bs4 import BeautifulSoup

from app.utils.text import clean_price
from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import map_property_type, parse_int


def _title_case_city(city: str) -> str:
    return " ".join(w.capitalize() for w in city.replace("-", " ").split())


def _pub_date_from_og_image(og_url: str) -> str | None:
    """Remax's Nuxt SSR payload hides all timestamps, but every listing has
    an `og:image` URL whose path is the base64-encoded CDN URL of the agent's
    photo on gestim.biz. That path embeds a 14-digit upload timestamp, e.g.

        https://cdn7.gestim.biz/custom/01858/foto/2025/11/20251103154416-994103-50.jpeg

    The first photo upload is a reliable proxy for when the listing went live
    (remax agents upload pictures as part of the creation flow). We return
    the ISO date — not time — since that's all we need downstream.
    """
    if not og_url:
        return None
    m = re.search(r"/([A-Za-z0-9]{30,})__?og_image", og_url)
    if not m:
        return None
    token = m.group(1)
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        return None
    tm = re.search(r"(20\d{12})", decoded)
    if not tm:
        return None
    t = tm.group(1)
    try:
        year, month, day = int(t[:4]), int(t[4:6]), int(t[6:8])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        pass
    return None


class RemaxSpider(BaseSpider):
    portal_name = "remax"
    base_url = "https://www.remax.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        contract = "Vendita" if params.listing_type == "sale" else "Affitto"
        city_slug = _title_case_city(params.city)
        url = f"{self.base_url}/trova/ricerca/{contract}/{city_slug}"
        if page > 1:
            url += f"?page={page}"
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        seen: set[str] = set()
        for link in soup.select('a[href*="/trova/immobile/"]'):
            href = link.get("href", "")
            if not href:
                continue
            if href.startswith("/"):
                href = self.base_url + href
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)
        return urls

    async def get_total_pages(self, html: str) -> int:
        """Parse the pagination bar. Remax shows numbered page buttons; we
        grab the highest visible number and cap at max_pages."""
        soup = BeautifulSoup(html, "lxml")
        pages: list[int] = []
        for el in soup.select("[class*='pagination'] *, nav a, nav button, nav li"):
            text = el.get_text(strip=True)
            if text.isdigit():
                pages.append(int(text))
        return max(pages) if pages else 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        soup = BeautifulSoup(html, "lxml")

        # --- source_id from code block or URL suffix
        source_id = None
        code_el = soup.select_one(".unit-overview__code")
        if code_el:
            text = code_el.get_text(" ", strip=True)
            m = re.search(r"([\w-]+)$", text)
            if m:
                source_id = m.group(1)
        if not source_id:
            m = re.search(r"_([\w-]+)$", url.rstrip("/"))
            if m:
                source_id = m.group(1)
            else:
                source_id = url.rstrip("/").split("/")[-1]

        # --- listing_type from Vendita/Affitto announce label
        announce_el = soup.select_one(".unit-overview__announce")
        announce = (announce_el.get_text(" ", strip=True) if announce_el else "").lower()
        listing_type = "rent" if "affitto" in announce else "sale"

        # --- property_type from the title block (Appartamento, Villa, ...)
        title_block_el = soup.select_one(".unit-overview__title")
        title_block = title_block_el.get_text(" ", strip=True) if title_block_el else ""
        property_type = self._remax_property_type(title_block)

        # --- Location string: "Via X, 12, Zona, Citta, PV" or "Citta, PV"
        location_el = soup.select_one(".unit-overview__location")
        location_raw = location_el.get_text(" ", strip=True) if location_el else ""
        address, city, zone, province = self._split_location(location_raw)

        # --- subtitle: "247mq, 5 locali"
        subtitle_el = soup.select_one(".unit-overview__subtitle")
        subtitle = subtitle_el.get_text(" ", strip=True) if subtitle_el else ""
        area_sqm = self._parse_area(subtitle)
        rooms = self._parse_rooms(subtitle)

        # --- price ("Richiedere quotazione" returns None)
        price = None
        price_el = soup.select_one(".unit-overview__price")
        if price_el:
            raw_price = price_el.get_text(" ", strip=True)
            if "richie" not in raw_price.lower():  # "Richiedere quotazione"
                price = clean_price(raw_price)

        # --- Feature grid (icons: #bedrooms, #bathrooms, #energyclass, #surface, #rooms)
        bedrooms = None
        bathrooms = None
        energy_class = None
        for feat in soup.select("div.unit-feature"):
            use = feat.select_one("use")
            href = use.get("xlink:href") if use else ""
            text = feat.get_text(" ", strip=True)
            if "bedrooms" in href:
                bedrooms = parse_int(text)
            elif "bathrooms" in href:
                bathrooms = parse_int(text)
            elif "energyclass" in href:
                # Strip the "Classe energetica" label so the regex doesn't
                # latch onto the 'C' in "Classe".
                cleaned = re.sub(r"classe\s+energetica", "", text, flags=re.IGNORECASE).strip()
                if cleaned and "non specif" not in cleaned.lower():
                    m = re.search(r"\b([A-G]\d?)\b", cleaned, re.IGNORECASE)
                    if m:
                        energy_class = m.group(1).upper()
            elif "surface" in href and area_sqm is None:
                m = re.search(r"(\d[\d.,]*)", text)
                if m:
                    try:
                        area_sqm = float(m.group(1).replace(".", "").replace(",", "."))
                    except ValueError:
                        pass
            elif "rooms" in href and rooms is None:
                rooms = parse_int(text)

        # --- description
        description = None
        desc_el = soup.select_one(
            ".unit-description, [class*='unit-description'], [itemprop='description']"
        )
        if not desc_el:
            desc_el = soup.select_one("[class*='description']")
        if desc_el:
            description = desc_el.get_text(" ", strip=True)[:4000]

        # --- cover image from og:image (property gallery is JS-hydrated).
        # The og:image URL path also encodes the agent's upload timestamp,
        # which we use below as a publication_date proxy.
        images: list[str] = []
        og_url = ""
        og = soup.find("meta", attrs={"property": "og:image"})
        if og:
            og_url = og.get("content", "")
            if og_url.startswith("http"):
                images.append(og_url)

        publication_date = _pub_date_from_og_image(og_url)

        # --- title: synthesize something informative
        title_parts: list[str] = []
        if title_block:
            title_parts.append(title_block)
        if subtitle:
            title_parts.append(subtitle)
        locality = zone or city
        if locality:
            title_parts.append(locality.title())
        title = " - ".join(title_parts) if title_parts else f"Annuncio remax {source_id}"

        page_text_lower = soup.get_text(" ", strip=True).lower()

        return ListingItem(
            source_portal=self.portal_name,
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=rooms,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=None,
            address=address,
            city=city or "unknown",
            zone=zone,
            province=province,
            lat=None,
            lng=None,
            property_type=property_type,
            listing_type=listing_type,
            images=images,
            energy_class=energy_class,
            has_elevator="ascensore" in page_text_lower or None,
            has_balcony="balcone" in page_text_lower or None,
            has_terrace="terrazz" in page_text_lower or None,
            has_garage=("garage" in page_text_lower or "box auto" in page_text_lower) or None,
            has_garden="giardino" in page_text_lower or None,
            publication_date=publication_date,
            raw_data={"location_raw": location_raw, "subtitle": subtitle},
        )

    @staticmethod
    def _split_location(raw: str) -> tuple[str | None, str | None, str | None, str | None]:
        """Parse remax location strings.

        Shapes seen in the wild:
          "Framura, SP"                            -> city + province
          "Corso Alcide De Gasperi, 312 S. Pasquale, Bari, BA"
            The civic number ("312") leads a token that continues with the
            zone ("S. Pasquale"). We reattach the number to the street and
            keep the zone text separate.

        Returns (address, city, zone, province).
        """
        if not raw:
            return None, None, None, None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return None, None, None, None

        province = None
        if len(parts[-1]) == 2 and parts[-1].isalpha() and parts[-1].isupper():
            province = parts.pop()

        city = None
        if parts:
            city = parts.pop().lower()

        # Reattach a leading civic number from the next token to the street.
        if len(parts) >= 2:
            m = re.match(r"^(\d+[A-Za-z]?)\s+(.+)$", parts[1])
            if m:
                parts[0] = f"{parts[0]}, {m.group(1)}"
                parts[1] = m.group(2).strip()

        zone = None
        address = None
        if len(parts) >= 2:
            zone = parts[-1]
            address = ", ".join(parts[:-1])
        elif len(parts) == 1:
            address = parts[0]

        return address, city, zone, province

    @staticmethod
    def _remax_property_type(title_block: str) -> str:
        """Map remax's title-block label to ListingItem.property_type.

        Remax sells more than apartments — hotels, land, commercial, etc. —
        so we widen the mapping beyond the shared helper.
        """
        if not title_block:
            return "apartment"
        lower = title_block.lower()
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

    @staticmethod
    def _parse_area(subtitle: str) -> float | None:
        if not subtitle:
            return None
        m = re.search(r"(\d[\d.,]*)\s*mq", subtitle, re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_rooms(subtitle: str) -> int | None:
        if not subtitle:
            return None
        m = re.search(r"(\d+)\s*local", subtitle, re.IGNORECASE)
        return int(m.group(1)) if m else None
