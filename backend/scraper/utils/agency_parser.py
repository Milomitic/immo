"""Shared listing-detail parser for agency-site spiders (Tecnocasa, Remax, Gabetti).

These portals all render listings with schema.org JSON-LD plus a
"caratteristiche" grid of label/value pairs. This module pulls every field
ListingItem can hold out of the detail page, so each spider only needs to
provide URL patterns and portal name.
"""

import re

from bs4 import BeautifulSoup

from app.utils.text import clean_area, clean_price
from scraper.items import ListingItem
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

_FLOOR_PLAN_HINTS = ("planimetr", "floorplan", "floor-plan", "floor_plan", "/plan/", "_plan.", "-plan.")


def _looks_like_floor_plan(url: str) -> bool:
    u = url.lower()
    return any(hint in u for hint in _FLOOR_PLAN_HINTS)


def parse_agency_detail(url: str, html: str, portal: str) -> ListingItem:
    """Parse an agency-site listing detail page into a fully-populated ListingItem."""
    soup = BeautifulSoup(html, "lxml")
    jsonld = extract_listing_jsonld(soup)
    features = parse_features(soup)
    page_text = soup.get_text(" ", strip=True)
    page_text_lower = page_text.lower()

    id_match = re.search(r"/(\d{4,})(?:[/?.]|$)", url)
    source_id = id_match.group(1) if id_match else url.rstrip("/").split("/")[-1]

    # --- Title
    title = None
    if jsonld:
        title = jsonld.get("name")
    if not title:
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else f"Annuncio {portal}"

    # --- Description (prefer JSON-LD, then itemprop, then class-based)
    description = None
    if jsonld:
        description = jsonld.get("description")
    if not description:
        desc_el = soup.select_one("[itemprop='description'], [class*='description'], [class*='Description']")
        if desc_el:
            description = desc_el.get_text(" ", strip=True)
    if description and len(description) > 4000:
        description = description[:4000]

    # --- Price
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
        price_raw = lookup(features, "prezzo")
        if price_raw:
            price = clean_price(price_raw)
    if price is None:
        for sel in ["[itemprop='price']", "[class*='price']", "[class*='Price']"]:
            el = soup.select_one(sel)
            if el:
                text = re.split(r"al mese|/mese|rata|mutuo", el.get_text(), flags=re.IGNORECASE)[0]
                price = clean_price(text)
                if price:
                    break

    # --- Surface
    area_sqm = parse_float_text(lookup(features, "superficie", "superf", "mq commerciali", "dimension"))
    if area_sqm is None and jsonld:
        fs = jsonld.get("floorSize") or {}
        if isinstance(fs, dict):
            area_sqm = parse_float(fs.get("value"))
    if area_sqm is None:
        for li in soup.select("[class*='feature'] li, [class*='detail'] li, [class*='info'] li, ul li"):
            text = li.get_text(" ", strip=True).lower()
            if ("mq" in text or "m²" in text) and "box" not in text and "cantina" not in text:
                area_sqm = clean_area(text)
                if area_sqm:
                    break

    # --- Rooms / bedrooms / bathrooms
    rooms = parse_int(lookup(features, "local", "vani", "numero di stanze"))
    bedrooms = parse_int(lookup(features, "camere", "camere da letto"))
    bathrooms = parse_int(lookup(features, "bagni"))
    if jsonld:
        if rooms is None:
            rooms = parse_int(jsonld.get("numberOfRooms"))
        if bedrooms is None:
            bedrooms = parse_int(jsonld.get("numberOfBedrooms"))
        if bathrooms is None:
            bathrooms = parse_int(jsonld.get("numberOfBathroomsTotal") or jsonld.get("numberOfFullBathrooms"))

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
    if year_built is None and jsonld:
        year_built = parse_int(jsonld.get("yearBuilt"))

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
    type_raw = lookup(features, "tipologia", "tipo immobile", "tipo di immobile")
    property_type = map_property_type(type_raw or (title.lower() if title else ""))

    # --- Publication date
    publication_date = None
    pub_raw = lookup(features, "data pubblicazione", "pubblicato", "inserito", "aggiornato", "data annuncio")
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

    # --- Address, city, zone, province, geo
    address = None
    city = "unknown"
    zone = None
    province = None
    lat = None
    lng = None
    if jsonld:
        addr = jsonld.get("address") or {}
        if isinstance(addr, dict):
            address = addr.get("streetAddress") or None
            locality = addr.get("addressLocality") or ""
            if locality:
                city = locality.lower()
            region = addr.get("addressRegion") or ""
            if region:
                province = region
        geo = jsonld.get("geo") or {}
        if isinstance(geo, dict):
            lat = parse_float(geo.get("latitude"))
            lng = parse_float(geo.get("longitude"))
    if not address:
        addr_raw = lookup(features, "indirizzo", "via")
        if addr_raw:
            address = addr_raw
    if city == "unknown":
        loc_raw = lookup(features, "localita", "comune", "citta")
        if loc_raw:
            city = loc_raw.strip().lower()
    if city == "unknown":
        # Agency URLs often encode the city slug
        city_match = re.search(r"/(?:vendita|affitto|immobili|casa)/[^/]*/([a-z][a-z0-9\-]+)", url)
        if city_match:
            city = city_match.group(1).replace("-", " ")
    zone_raw = lookup(features, "zona", "quartiere")
    if zone_raw:
        zone = zone_raw

    # --- Images
    raw_images: list[str] = []
    if jsonld:
        img = jsonld.get("image")
        if isinstance(img, list):
            raw_images = [str(i) for i in img if i]
        elif isinstance(img, str):
            raw_images = [img]
    if not raw_images:
        for img in soup.select("[class*='gallery'] img, [class*='Gallery'] img, [class*='carousel'] img, [class*='slider'] img, picture img"):
            src = img.get("data-src") or img.get("src", "")
            if src and src.startswith("http"):
                raw_images.append(src)
    if not raw_images:
        for source in soup.select("picture source"):
            srcset = source.get("srcset", "")
            if srcset and srcset.startswith("http"):
                raw_images.append(srcset.split(" ")[0])
    # Also look for elements explicitly labelled as floor plans
    for el in soup.select("[class*='planimetria'] img, [class*='Planimetria'] img, [class*='floorplan'] img, [class*='FloorPlan'] img, [alt*='planimetria' i], [alt*='floor plan' i]"):
        src = el.get("data-src") or el.get("src", "")
        if src and src.startswith("http") and src not in raw_images:
            raw_images.append(src)

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
    images = images[:20]
    floor_plans = floor_plans[:10]

    # --- Feature flags
    has_elevator = "ascensore" in page_text_lower
    has_balcony = "balcone" in page_text_lower
    has_terrace = "terrazz" in page_text_lower
    has_garage = "garage" in page_text_lower or "box auto" in page_text_lower or "posto auto" in page_text_lower
    has_garden = "giardino" in page_text_lower

    listing_type = "rent" if "/affitto" in url.lower() else "sale"

    return ListingItem(
        source_portal=portal,
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
        city=city or "unknown",
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
