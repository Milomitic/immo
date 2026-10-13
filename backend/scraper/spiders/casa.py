import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.utils.text import clean_area, clean_price
from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import (
    detect_feature,
    extract_publication_date_from_text,
    lookup,
    map_condition,
    map_property_type,
    parse_features,
    parse_float_text,
    parse_int,
    parse_italian_date,
    yes_no,
)
from scraper.utils.jsonld import extract_listing_jsonld, parse_float, parse_price


def _extract_next_data(soup: BeautifulSoup) -> dict | None:
    """Extract the __NEXT_DATA__ JSON from casa.it's Next.js pages.

    Returns the ``pdp`` (product detail page) object which contains the full
    listing payload: gallery images, address with lat/lng, mainFeatures,
    energy class, modification date, and structured feature lists.
    """
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
        return data.get("props", {}).get("pageProps", {}).get("pdp")
    except (json.JSONDecodeError, ValueError):
        return None

def _structured_features(pdp: dict | None) -> tuple[dict[str, list], list[str]]:
    """Flatten ``pdp.features.featureLists`` into ``{label: values}`` plus
    the free tags of "Altre caratteristiche" (["balcone", "portineria"]).
    Labels are lowercased so callers can match them directly."""
    labels: dict[str, list] = {}
    tags: list[str] = []
    if not pdp:
        return labels, tags
    for group in (pdp.get("features") or {}).get("featureLists") or []:
        for item in group.get("items") or []:
            label = str(item.get("label") or "").strip().lower()
            values = item.get("values") or []
            if item.get("displayType") == "tag":
                tags.extend(str(v).lower() for v in values if isinstance(v, str))
            elif label:
                labels[label] = values
    # Tags like "balcone" behave like a label with a "present" value.
    for tag in tags:
        labels.setdefault(tag, ["sì"])
    return labels, tags


def _presence(values: list) -> bool | None:
    """A structured value counts as present unless it's an explicit no:
    "sì" → True, "no" → False, "privato"/"condominiale"/1 → True."""
    if not values:
        return None
    v = values[0]
    if isinstance(v, dict):
        v = v.get("main")
    known = yes_no(v)
    if known is not None:
        return known
    return bool(str(v).strip()) if v is not None else None


_FLOOR_PLAN_HINTS = ("planimetr", "floorplan", "floor-plan", "floor_plan", "/plan/", "_plan.", "-plan.")


def _looks_like_floor_plan(url: str) -> bool:
    u = url.lower()
    return any(hint in u for hint in _FLOOR_PLAN_HINTS)


# Feature bullets of the page body, the last resort for surface/rooms/baths.
_FEATURE_ITEMS = "[class*='info'] li, [class*='feature'] li, [class*='Feature'] li"


# Each extractor below reads one group of fields, trying the sources from
# the most to the least reliable: __NEXT_DATA__ ``pdp``, JSON-LD, the
# page's label/value pairs (``features``), then the page text.


def _title(soup: BeautifulSoup, jsonld: dict | None) -> str:
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else None
    if not title and jsonld:
        title = jsonld.get("name")
    return title or "Annuncio casa.it"


def _price(soup: BeautifulSoup, jsonld: dict | None) -> float | None:
    if jsonld:
        offers = jsonld.get("offers") or {}
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            price = parse_price(
                offers.get("price") or offers.get("priceSpecification", {}).get("price")
            )
            if price is not None:
                return price
    price_el = soup.select_one("[class*='price'], [class*='Price']")
    if not price_el:
        return None
    # Skip the mortgage-rate fragment ("€ 350.000 tua da 1.200 al mese").
    price_text = re.split(r"tua da|al mese|/mese|rata", price_el.get_text(), flags=re.IGNORECASE)[0]
    return clean_price(price_text)


def _description(soup: BeautifulSoup, jsonld: dict | None) -> str | None:
    description = jsonld.get("description") if jsonld else None
    if not description:
        desc_el = soup.select_one("[class*='description'], [class*='Description'], [itemprop='description']")
        if desc_el:
            description = desc_el.get_text(" ", strip=True)
    if description and len(description) > 4000:
        description = description[:4000]
    return description


def _area(soup: BeautifulSoup, jsonld: dict | None, features: dict[str, str]) -> float | None:
    area_sqm = parse_float_text(lookup(features, "superficie", "superf", "mq commerciali", "dimension"))
    if area_sqm is None and jsonld:
        fs = jsonld.get("floorSize") or {}
        if isinstance(fs, dict):
            area_sqm = parse_float(fs.get("value"))
    if area_sqm is None:
        # last-resort: the first bullet with a surface that isn't the box's
        # or the cellar's
        for li in soup.select(_FEATURE_ITEMS):
            text = li.get_text(strip=True).lower()
            if ("mq" in text or "m²" in text) and "box" not in text and "cantina" not in text:
                area_sqm = clean_area(text)
                if area_sqm:
                    break
    return area_sqm


def _room_counts(
    soup: BeautifulSoup, features: dict[str, str]
) -> tuple[int | None, int | None, int | None]:
    """(rooms, bedrooms, bathrooms)."""
    rooms = parse_int(lookup(features, "local", "vani", "stanze totali"))
    bedrooms = parse_int(lookup(features, "camere", "camere da letto"))
    bathrooms = parse_int(lookup(features, "bagni"))
    if rooms is None or bathrooms is None:
        for li in soup.select(_FEATURE_ITEMS):
            text = li.get_text(strip=True).lower()
            if rooms is None and ("local" in text or "vani" in text):
                m = re.search(r"\d+", text)
                if m:
                    rooms = int(m.group())
            elif bathrooms is None and "bagn" in text:
                m = re.search(r"\d+", text)
                if m:
                    bathrooms = int(m.group())
    return rooms, bedrooms, bathrooms


def _floors(features: dict[str, str]) -> tuple[str | None, int | None]:
    """(floor, total_floors) — "3 su 6" carries both."""
    floor_raw = lookup(features, "piano")
    floor = None
    total_floors = None
    if floor_raw:
        floor = floor_raw.strip()
        m = re.search(r"su\s+(\d+)", floor_raw, re.IGNORECASE)
        if m:
            total_floors = int(m.group(1))
    if total_floors is None:
        total_floors = parse_int(lookup(features, "piani edificio", "piani totali", "totale piani"))
    return floor, total_floors


# A class letter standing on its own: "A4", "classe g", "G (≥ 175 kWh)" —
# not the "d" of "n.d." nor the "E" of "Esente", which used to read as
# classes D and E.
_ENERGY_CLASS = r"(?<![a-z.])([A-G]\d?)(?![a-z])"


def _energy_class(features: dict[str, str], page_text: str) -> str | None:
    ec_raw = lookup(features, "classe energetica", "efficienza energetica")
    if ec_raw:
        m = re.search(_ENERGY_CLASS, ec_raw, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    m = re.search(r"classe\s+energetica\s*[:\s]*" + _ENERGY_CLASS, page_text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _publication_date(
    pdp: dict | None, jsonld: dict | None, features: dict[str, str], page_text: str
) -> str | None:
    # __NEXT_DATA__ exposes a "modified" field like "13 Aprile 2026"
    if pdp and pdp.get("modified"):
        date = parse_italian_date(str(pdp["modified"]))
        if date:
            return date
    pub_raw = lookup(features, "data pubblicazione", "pubblicato", "inserito", "aggiornato")
    if pub_raw:
        date = parse_italian_date(pub_raw)
        if date:
            return date
    if jsonld:
        for key in ("datePosted", "datePublished", "uploadDate", "dateCreated", "dateModified"):
            val = jsonld.get(key)
            if val:
                date = parse_italian_date(str(val))
                if date:
                    return date
    return extract_publication_date_from_text(page_text)


def _gallery(pdp: dict | None) -> tuple[list[str], list[str]]:
    """(photos, floor plans) from __NEXT_DATA__: the full gallery, as
    entries ``{mediaid, alt, type}`` plus a host prefix."""
    photos: list[str] = []
    plans: list[str] = []
    if not pdp:
        return photos, plans
    media = pdp.get("media") or {}
    host = (media.get("hostImages") or "").rstrip("/")
    gallery = media.get("gallery") or media.get("newGalleryConf", {}).get("slides") or []
    for entry in gallery:
        if not isinstance(entry, dict):
            continue
        mid = entry.get("mediaid")
        if not mid:
            continue
        # The CDN expects ``{host}/{size}/listing/{mediaid}`` — without
        # the ``/listing/`` segment the gateway returns 400 "Invalid
        # URI format". Easy to miss because nothing in __NEXT_DATA__
        # tells you about it; only inspecting the rendered HTML does.
        img_url = f"{host}/800x600/listing/{mid}" if host else ""
        if not img_url.startswith("http"):
            continue
        # casa.it tags floor plans as ``"floorplan"`` in English —
        # we previously checked for the Italian ``"planimetry"`` and
        # so silently dropped every floor plan into the photos list.
        # Both forms accepted now plus a URL/path heuristic as
        # last resort.
        etype = (entry.get("type") or "").lower()
        if etype in ("floorplan", "planimetry") or _looks_like_floor_plan(mid):
            plans.append(img_url)
        else:
            photos.append(img_url)
    return photos, plans


def _dom_images(soup: BeautifulSoup) -> list[str]:
    """Fallback when __NEXT_DATA__ has no gallery (rare): gallery markup,
    then <picture> sources, then og:image."""
    images = []
    for img_el in soup.select("[class*='gallery'] img, [class*='Gallery'] img, [class*='carousel'] img, [class*='slider'] img, picture img"):
        src = img_el.get("data-src") or img_el.get("src", "")
        if src and src.startswith("http") and "placeholder" not in src:
            images.append(src)
    if not images:
        for source in soup.select("picture source"):
            srcset = source.get("srcset", "")
            if srcset and srcset.startswith("http"):
                images.append(srcset.split(" ")[0])
    if not images:
        og = soup.find("meta", attrs={"property": "og:image"})
        if og:
            og_url = og.get("content", "")
            if og_url.startswith("http") and "placeholder" not in og_url:
                images.append(og_url)
    return images


def _images(soup: BeautifulSoup, pdp: dict | None) -> tuple[list[str], list[str]]:
    """(images, floor_plans), deduplicated and capped."""
    raw_images, raw_floor_plans = _gallery(pdp)
    if not raw_images:
        raw_images = _dom_images(soup)

    seen: set[str] = set()
    images: list[str] = []
    floor_plans: list[str] = []
    for url in raw_images:
        if url in seen:
            continue
        seen.add(url)
        if _looks_like_floor_plan(url):
            floor_plans.append(url)
        else:
            images.append(url)
    for url in raw_floor_plans:
        if url not in seen:
            seen.add(url)
            floor_plans.append(url)
    return images[:30], floor_plans[:10]


def _coord(value) -> float | None:
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


@dataclass
class _Location:
    address: str | None = None
    city: str = "unknown"
    zone: str | None = None
    province: str | None = None
    lat: float | None = None
    lng: float | None = None


def _location(
    soup: BeautifulSoup,
    pdp: dict | None,
    jsonld: dict | None,
    features: dict[str, str],
    title: str,
) -> _Location:
    loc = _Location()

    # Primary source: __NEXT_DATA__ has precise address with coords
    pdp_addr = (pdp or {}).get("address") or {}
    if isinstance(pdp_addr, dict):
        loc.address = pdp_addr.get("street") or None
        town = pdp_addr.get("town") or ""
        if town:
            loc.city = town.lower()
        loc.zone = pdp_addr.get("zone") or pdp_addr.get("block") or None
        loc.province = pdp_addr.get("province") or None
        loc.lat = _coord(pdp_addr.get("lat"))
        loc.lng = _coord(pdp_addr.get("lon"))

    # Fallback: JSON-LD
    if loc.city == "unknown" and jsonld:
        addr = jsonld.get("address") or {}
        if isinstance(addr, dict):
            if not loc.address:
                loc.address = addr.get("streetAddress") or None
            locality = addr.get("addressLocality") or ""
            if locality:
                loc.city = locality.lower()
            if not loc.province:
                loc.province = addr.get("addressRegion") or None
        if loc.lat is None or loc.lng is None:
            geo = jsonld.get("geo") or {}
            if isinstance(geo, dict):
                loc.lat = parse_float(geo.get("latitude"))
                loc.lng = parse_float(geo.get("longitude"))

    # Last resorts: page features, the title ("… in Via X … a Bari"),
    # the breadcrumb.
    if not loc.address:
        addr_raw = lookup(features, "indirizzo", "via")
        if addr_raw:
            loc.address = addr_raw
        else:
            addr_match = re.search(r"in\s+(Via|Viale|Corso|Piazza|Largo|Strada)\s+[^,]+", title, re.IGNORECASE)
            if addr_match:
                loc.address = addr_match.group(0).replace("in ", "", 1).strip()
    if loc.city == "unknown":
        city_match = re.search(r"\ba\s+([A-Z][a-zA-Z\s]+)$", title)
        if city_match:
            loc.city = city_match.group(1).strip().lower()
    if loc.city == "unknown":
        for bc in soup.select("[class*='breadcrumb'] a, [class*='Breadcrumb'] a"):
            text = bc.get_text(strip=True)
            if text and text.lower() not in ("home", "casa.it", "vendita", "affitto", "case", "immobili", "torna ai risultati", ""):
                loc.city = text.lower()
                break
    zone_raw = lookup(features, "zona", "quartiere")
    if zone_raw:
        loc.zone = zone_raw
    return loc


def _flags(pdp: dict | None, description: str | None) -> dict[str, bool | None]:
    """The has_* feature flags. Structured list first, then the description;
    never the whole page — its sidebar facets and SEO links mention
    "giardino"/"ascensore" on every listing (82% of casa.it listings had
    has_elevator=True this way, only 6% mentioned it)."""
    labels, tags = _structured_features(pdp)
    flag_text = " ".join(filter(None, [description, " ".join(tags)]))

    def flag(label_names: tuple[str, ...], *keywords: str) -> bool | None:
        for name in label_names:
            if name in labels:
                return _presence(labels[name])
        return detect_feature(flag_text, *keywords)

    return {
        "has_elevator": flag(("ascensore",), "ascensore"),
        "has_balcony": flag(("balcone", "balconi"), "balcon"),
        "has_terrace": flag(("terrazzo", "terrazza", "terrazzi"), "terrazz"),
        "has_garage": flag(("box", "garage", "box auto", "posto auto"), "garage", "box auto", "posto auto"),
        "has_garden": flag(("giardino",), "giardin"),
    }


def _listing_type(pdp: dict | None, url: str) -> str:
    # The pdp "channel" is authoritative; the old page-text sniff only
    # looked at the first 500 chars, which include the nav menu.
    channel = str((pdp or {}).get("channel") or "").lower()
    if channel in ("rent", "affitto", "rental"):
        return "rent"
    if channel in ("sale", "vendita"):
        return "sale"
    return "rent" if "affitto" in url.lower() else "sale"


class CasaSpider(BaseSpider):
    portal_name = "casa"
    base_url = "https://www.casa.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        # casa.it uses path-based city URLs. The /srp/?l=<city> form does
        # NOT filter by city and silently returns national results.
        listing_type_map = {"sale": "vendita", "rent": "affitto"}
        lt = listing_type_map.get(params.listing_type, "vendita")
        city_slug = params.city.lower().replace(" ", "-")

        query_parts: list[str] = []
        if params.price_min:
            query_parts.append(f"priceMin={int(params.price_min)}")
        if params.price_max:
            query_parts.append(f"priceMax={int(params.price_max)}")
        if params.area_min:
            query_parts.append(f"surfaceMin={int(params.area_min)}")
        if params.area_max:
            query_parts.append(f"surfaceMax={int(params.area_max)}")
        if page > 1:
            query_parts.append(f"page={page}")

        url = f"{self.base_url}/{lt}/residenziale/{city_slug}/"
        if query_parts:
            url += "?" + "&".join(query_parts)
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []

        # Casa.it uses cards with class csaSrpcard and links to /immobili/ID/
        for card in soup.select("[class*='csaSrpcard']"):
            for link in card.find_all("a", href=True):
                href = link["href"]
                if "/immobili/" in href:
                    if href.startswith("/"):
                        href = self.base_url + href
                    if href not in urls:
                        urls.append(href)

        return urls

    async def parse_search_results_with_prices(
        self, html: str
    ) -> list[tuple[str, float | None]]:
        """Pair each result URL with the price shown on the card.

        Casa.it cards render the price as a string like ``"€ 250.000"``
        inside the same wrapper that holds the listing link. We co-walk
        the DOM so the price stays attached to *its* card even when the
        page contains banner-ads and unrelated promotional cards.
        """
        soup = BeautifulSoup(html, "lxml")
        out: list[tuple[str, float | None]] = []
        seen: set[str] = set()
        for card in soup.select("[class*='csaSrpcard']"):
            href = None
            for link in card.find_all("a", href=True):
                if "/immobili/" in link["href"]:
                    href = link["href"]
                    break
            if not href:
                continue
            if href.startswith("/"):
                href = self.base_url + href
            if href in seen:
                continue
            seen.add(href)

            # Price text — typically "€ 250.000" or "250.000 €" inside an
            # element whose class contains "price" or "Price"; we search
            # the card's text as a robust fallback against class hashing.
            price = None
            price_el = card.select_one("[class*='price'], [class*='Price']")
            blob = (price_el.get_text(" ", strip=True) if price_el else card.get_text(" ", strip=True))
            m = re.search(r"€\s*([\d.,]+)|([\d.,]+)\s*€", blob)
            if m:
                raw = (m.group(1) or m.group(2) or "").replace(".", "").replace(",", "")
                if raw.isdigit():
                    try:
                        price = float(raw)
                    except ValueError:
                        price = None
            out.append((href, price))
        return out

    async def get_total_pages(self, html: str) -> int:
        """Estimate the page count for casa.it search results.

        Casa.it uses CSS-in-JS hashed class names, so we can't anchor on
        stable selectors. Two reliable signals instead:
          1. The "875 annunci" header text — most accurate, gives the
             exact result count.
          2. The pagination strip ("1 2 3 ... 9 Successiva") with a
             lowercase ``pagin`` substring in the class name. It only shows
             a window of pages, so it's a lower bound — fallback only.

        Page size is 20. Returns the site's real page count; the run caps
        it at ``max_pages`` and flags the truncation.
        """
        # 1. Total count in header text (e.g. "875 annunci")
        m = re.search(r"(\d[\d.]*)\s*annunci", html, re.IGNORECASE)
        if m:
            total = int(m.group(1).replace(".", ""))
            return max(1, (total + 19) // 20)

        # 2. Pagination links (note: class is lowercase ``pagin``,
        #    NOT ``pagination``/``Pagination``).
        soup = BeautifulSoup(html, "lxml")
        for sel in ["[class*='pagin'] a", "[class*='Paging'] a"]:
            pages = [
                int(el.get_text(strip=True))
                for el in soup.select(sel)
                if el.get_text(strip=True).isdigit()
            ]
            if pages:
                return max(pages)

        return 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        soup = BeautifulSoup(html, "lxml")

        match = re.search(r"/immobili/(\d+)", url)
        source_id = match.group(1) if match else url.rstrip("/").split("/")[-1]

        pdp = _extract_next_data(soup)
        jsonld = extract_listing_jsonld(soup)
        features = parse_features(soup)
        page_text = soup.get_text(" ", strip=True)

        title = _title(soup, jsonld)
        description = _description(soup, jsonld)
        rooms, bedrooms, bathrooms = _room_counts(soup, features)
        floor, total_floors = _floors(features)
        images, floor_plans = _images(soup, pdp)
        loc = _location(soup, pdp, jsonld, features, title)
        type_raw = lookup(features, "tipologia", "tipo immobile")

        return ListingItem(
            source_portal="casa",
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=_price(soup, jsonld),
            area_sqm=_area(soup, jsonld, features),
            rooms=rooms,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=floor,
            total_floors=total_floors,
            address=loc.address,
            city=loc.city,
            zone=loc.zone,
            province=loc.province,
            lat=loc.lat,
            lng=loc.lng,
            property_type=map_property_type(type_raw or title.lower()),
            listing_type=_listing_type(pdp, url),
            images=images,
            floor_plans=floor_plans,
            energy_class=_energy_class(features, page_text),
            condition=map_condition(lookup(features, "stato", "condizione")),
            heating=lookup(features, "riscaldamento"),
            **_flags(pdp, description),
            condominium_fees=parse_float_text(
                lookup(features, "spese condominiali", "spese condom", "condominio")
            ),
            year_built=parse_int(lookup(features, "anno di costruzione", "anno costruzione", "costruzione")),
            publication_date=_publication_date(pdp, jsonld, features, page_text),
            raw_data={"features": features},
        )
