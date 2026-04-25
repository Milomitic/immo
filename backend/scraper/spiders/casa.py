import json
import re

from bs4 import BeautifulSoup

from app.utils.text import clean_area, clean_price
from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import (
    extract_publication_date_from_text,
    lookup,
    map_condition,
    map_property_type,
    parse_features,
    parse_float_text,
    parse_int,
    parse_italian_date,
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

_FLOOR_PLAN_HINTS = ("planimetr", "floorplan", "floor-plan", "floor_plan", "/plan/", "_plan.", "-plan.")


def _looks_like_floor_plan(url: str) -> bool:
    u = url.lower()
    return any(hint in u for hint in _FLOOR_PLAN_HINTS)


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

    async def get_total_pages(self, html: str) -> int:
        """Estimate the page count for casa.it search results.

        Casa.it uses CSS-in-JS hashed class names, so we can't anchor on
        stable selectors. Two reliable signals instead:
          1. The "875 annunci" header text — most accurate, gives the
             exact result count.
          2. The pagination strip ("1 2 3 ... 9 Successiva") with a
             lowercase ``pagin`` substring in the class name.

        Page size is 20 and we cap at 50 pages to keep one scrape bounded.
        """
        # 1. Total count in header text (e.g. "875 annunci")
        m = re.search(r"(\d[\d.]*)\s*annunci", html, re.IGNORECASE)
        if m:
            total = int(m.group(1).replace(".", ""))
            return min((total + 19) // 20, 50)

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
                return min(max(pages), 50)

        return 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        soup = BeautifulSoup(html, "lxml")

        match = re.search(r"/immobili/(\d+)", url)
        source_id = match.group(1) if match else url.rstrip("/").split("/")[-1]

        pdp = _extract_next_data(soup)
        jsonld = extract_listing_jsonld(soup)
        features = parse_features(soup)
        page_text = soup.get_text(" ", strip=True)
        page_text_lower = page_text.lower()

        # --- Title
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else None
        if not title and jsonld:
            title = jsonld.get("name")
        if not title:
            title = "Annuncio casa.it"

        # --- Price (skip mortgage-rate fragments)
        price = None
        if jsonld:
            offers = jsonld.get("offers") or {}
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = parse_price(
                    offers.get("price") or offers.get("priceSpecification", {}).get("price")
                )
        if price is None:
            price_el = soup.select_one("[class*='price'], [class*='Price']")
            if price_el:
                price_text = re.split(r"tua da|al mese|/mese|rata", price_el.get_text(), flags=re.IGNORECASE)[0]
                price = clean_price(price_text)

        # --- Description
        description = None
        if jsonld:
            description = jsonld.get("description")
        if not description:
            desc_el = soup.select_one("[class*='description'], [class*='Description'], [itemprop='description']")
            if desc_el:
                description = desc_el.get_text(" ", strip=True)
        if description and len(description) > 4000:
            description = description[:4000]

        # --- Surface (superficie)
        area_sqm = parse_float_text(lookup(features, "superficie", "superf", "mq commerciali", "dimension"))
        if area_sqm is None and jsonld:
            fs = jsonld.get("floorSize") or {}
            if isinstance(fs, dict):
                area_sqm = parse_float(fs.get("value"))
        if area_sqm is None:
            # last-resort: walk li elements and pick first with mq
            for li in soup.select("[class*='info'] li, [class*='feature'] li, [class*='Feature'] li"):
                text = li.get_text(strip=True).lower()
                if ("mq" in text or "m²" in text) and "box" not in text and "cantina" not in text:
                    area_sqm = clean_area(text)
                    if area_sqm:
                        break

        # --- Rooms, bedrooms, bathrooms
        rooms = parse_int(lookup(features, "local", "vani", "stanze totali"))
        bedrooms = parse_int(lookup(features, "camere", "camere da letto"))
        bathrooms = parse_int(lookup(features, "bagni"))
        if rooms is None or bathrooms is None:
            for li in soup.select("[class*='info'] li, [class*='feature'] li, [class*='Feature'] li"):
                text = li.get_text(strip=True).lower()
                if rooms is None and ("local" in text or "vani" in text):
                    m = re.search(r"\d+", text)
                    if m:
                        rooms = int(m.group())
                elif bathrooms is None and "bagn" in text:
                    m = re.search(r"\d+", text)
                    if m:
                        bathrooms = int(m.group())

        # --- Floor & total floors
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

        # --- Year built
        year_built = parse_int(lookup(features, "anno di costruzione", "anno costruzione", "costruzione"))

        # --- Condominium fees
        condominium_fees = parse_float_text(lookup(features, "spese condominiali", "spese condom", "condominio"))

        # --- Heating, condition, energy class
        heating = lookup(features, "riscaldamento")
        condition = map_condition(lookup(features, "stato", "condizione"))
        energy_class = None
        ec_raw = lookup(features, "classe energetica", "efficienza energetica")
        if ec_raw:
            m = re.search(r"([A-G]\d?)", ec_raw, re.IGNORECASE)
            if m:
                energy_class = m.group(1).upper()
        if not energy_class:
            m = re.search(r"classe\s+energetica\s*[:\s]*([A-G]\d?)", page_text, re.IGNORECASE)
            if m:
                energy_class = m.group(1).upper()

        # --- Property type
        type_raw = lookup(features, "tipologia", "tipo immobile")
        property_type = map_property_type(type_raw or title.lower())

        # --- Publication date
        publication_date = None
        # __NEXT_DATA__ exposes a "modified" field like "13 Aprile 2026"
        if pdp:
            modified_raw = pdp.get("modified")
            if modified_raw:
                publication_date = parse_italian_date(str(modified_raw))
        if not publication_date:
            pub_raw = lookup(features, "data pubblicazione", "pubblicato", "inserito", "aggiornato")
            if pub_raw:
                publication_date = parse_italian_date(pub_raw)
        if not publication_date and jsonld:
            for key in ("datePosted", "datePublished", "uploadDate", "dateCreated", "dateModified"):
                val = jsonld.get(key)
                if val:
                    publication_date = parse_italian_date(str(val))
                    if publication_date:
                        break
        if not publication_date:
            publication_date = extract_publication_date_from_text(page_text)

        # --- Images & floor plans
        # Primary source: __NEXT_DATA__ has the full gallery with media IDs
        # and a host prefix. Each entry is {mediaid, alt, type} where type
        # is "photo" or "planimetry".
        raw_images: list[str] = []
        raw_floor_plans: list[str] = []

        if pdp:
            media = pdp.get("media") or {}
            host = (media.get("hostImages") or "").rstrip("/")
            gallery = media.get("gallery") or media.get("newGalleryConf", {}).get("slides") or []
            for entry in gallery:
                if not isinstance(entry, dict):
                    continue
                mid = entry.get("mediaid")
                if not mid:
                    continue
                img_url = f"{host}/800x600/{mid}" if host else ""
                if not img_url.startswith("http"):
                    continue
                if entry.get("type") == "planimetry" or _looks_like_floor_plan(mid):
                    raw_floor_plans.append(img_url)
                else:
                    raw_images.append(img_url)

        # Fallback: DOM-based extraction (rare — only when __NEXT_DATA__ absent)
        if not raw_images:
            for img_el in soup.select("[class*='gallery'] img, [class*='Gallery'] img, [class*='carousel'] img, [class*='slider'] img, picture img"):
                src = img_el.get("data-src") or img_el.get("src", "")
                if src and src.startswith("http") and "placeholder" not in src:
                    raw_images.append(src)
        if not raw_images:
            for source in soup.select("picture source"):
                srcset = source.get("srcset", "")
                if srcset and srcset.startswith("http"):
                    raw_images.append(srcset.split(" ")[0])
        # og:image as last resort
        if not raw_images:
            og = soup.find("meta", attrs={"property": "og:image"})
            if og:
                og_url = og.get("content", "")
                if og_url.startswith("http") and "placeholder" not in og_url:
                    raw_images.append(og_url)

        seen: set[str] = set()
        images: list[str] = []
        floor_plans: list[str] = []
        for url_ in raw_images:
            if url_ in seen:
                continue
            seen.add(url_)
            if _looks_like_floor_plan(url_):
                floor_plans.append(url_)
            else:
                images.append(url_)
        for url_ in raw_floor_plans:
            if url_ not in seen:
                seen.add(url_)
                floor_plans.append(url_)
        images = images[:30]
        floor_plans = floor_plans[:10]

        # --- Address, city, zone, province, geo
        address = None
        city = "unknown"
        zone = None
        province = None
        lat = None
        lng = None

        # Primary source: __NEXT_DATA__ has precise address with coords
        if pdp:
            pdp_addr = pdp.get("address") or {}
            if isinstance(pdp_addr, dict):
                address = pdp_addr.get("street") or None
                town = pdp_addr.get("town") or ""
                if town:
                    city = town.lower()
                zone = pdp_addr.get("zone") or pdp_addr.get("block") or None
                province = pdp_addr.get("province") or None
                try:
                    lat = float(pdp_addr["lat"]) if pdp_addr.get("lat") else None
                except (TypeError, ValueError):
                    lat = None
                try:
                    lng = float(pdp_addr["lon"]) if pdp_addr.get("lon") else None
                except (TypeError, ValueError):
                    lng = None

        # Fallback: JSON-LD
        if city == "unknown" and jsonld:
            addr = jsonld.get("address") or {}
            if isinstance(addr, dict):
                if not address:
                    address = addr.get("streetAddress") or None
                locality = addr.get("addressLocality") or ""
                if locality:
                    city = locality.lower()
                if not province:
                    province = addr.get("addressRegion") or None
            if lat is None or lng is None:
                geo = jsonld.get("geo") or {}
                if isinstance(geo, dict):
                    lat = parse_float(geo.get("latitude"))
                    lng = parse_float(geo.get("longitude"))

        if not address:
            addr_raw = lookup(features, "indirizzo", "via")
            if addr_raw:
                address = addr_raw
            else:
                addr_match = re.search(r"in\s+(Via|Viale|Corso|Piazza|Largo|Strada)\s+[^,]+", title, re.IGNORECASE)
                if addr_match:
                    address = addr_match.group(0).replace("in ", "", 1).strip()
        if city == "unknown":
            city_match = re.search(r"\ba\s+([A-Z][a-zA-Z\s]+)$", title)
            if city_match:
                city = city_match.group(1).strip().lower()
        if city == "unknown":
            for bc in soup.select("[class*='breadcrumb'] a, [class*='Breadcrumb'] a"):
                text = bc.get_text(strip=True)
                if text and text.lower() not in ("home", "casa.it", "vendita", "affitto", "case", "immobili", "torna ai risultati", ""):
                    city = text.lower()
                    break
        zone_raw = lookup(features, "zona", "quartiere")
        if zone_raw:
            zone = zone_raw

        # --- Feature flags
        has_elevator = "ascensore" in page_text_lower
        has_balcony = "balcone" in page_text_lower
        has_terrace = "terrazz" in page_text_lower
        has_garage = "garage" in page_text_lower or "box auto" in page_text_lower or "posto auto" in page_text_lower
        has_garden = "giardino" in page_text_lower

        listing_type = "rent" if "affitto" in url.lower() or "affitto" in page_text_lower[:500] else "sale"

        return ListingItem(
            source_portal="casa",
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=rooms,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=floor,
            total_floors=total_floors,
            address=address,
            city=city,
            zone=zone,
            province=province,
            lat=lat,
            lng=lng,
            property_type=property_type,
            listing_type=listing_type,
            images=images,
            floor_plans=floor_plans,
            energy_class=energy_class,
            condition=condition,
            heating=heating,
            has_elevator=has_elevator,
            has_balcony=has_balcony,
            has_terrace=has_terrace,
            has_garage=has_garage,
            has_garden=has_garden,
            condominium_fees=condominium_fees,
            year_built=year_built,
            publication_date=publication_date,
            raw_data={"features": features},
        )
