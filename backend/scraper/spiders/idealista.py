import json
import re

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.playwright_base import PlaywrightSpider
from scraper.spiders.base import SearchParams
from app.utils.text import clean_price, clean_area


class IdealistaSpider(PlaywrightSpider):
    portal_name = "idealista"
    base_url = "https://www.idealista.it"

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        listing_type_map = {"sale": "vendita-case", "rent": "affitto-case"}
        lt = listing_type_map.get(params.listing_type, "vendita-case")
        url = f"{self.base_url}/{lt}/{params.city}/"

        if page > 1:
            # Idealista uses /pagina-N.htm format
            url = f"{self.base_url}/{lt}/{params.city}/pagina-{page}.htm"

        query_parts = []
        if params.price_min:
            query_parts.append(f"minPrice={int(params.price_min)}")
        if params.price_max:
            query_parts.append(f"maxPrice={int(params.price_max)}")
        if params.area_min:
            query_parts.append(f"minSize={int(params.area_min)}")
        if params.area_max:
            query_parts.append(f"maxSize={int(params.area_max)}")

        if query_parts:
            url += "?" + "&".join(query_parts)
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []

        for article in soup.select("article.item"):
            link = article.select_one("a.item-link")
            if link:
                href = link.get("href", "")
                if href.startswith("/"):
                    href = self.base_url + href
                if href not in urls:
                    urls.append(href)

        return urls

    async def get_total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, "lxml")

        # Look for pagination
        pagination = soup.select(".pagination a, .pagination li")
        pages = []
        for el in pagination:
            text = el.get_text(strip=True)
            if text.isdigit():
                pages.append(int(text))

        if pages:
            return min(max(pages), 60)  # Idealista caps at ~60 pages
        return 1

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        soup = BeautifulSoup(html, "lxml")

        # Extract source_id from URL
        match = re.search(r"/(\d+)/?", url)
        source_id = match.group(1) if match else url.rstrip("/").split("/")[-1]

        title_el = soup.select_one("h1.main-info__title-main, .detail-title-container h1")
        title = title_el.get_text(strip=True) if title_el else "Untitled"

        # Price
        price = None
        price_el = soup.select_one(".info-data-price span, .price-features__container .flex-feature-details span")
        if price_el:
            price = clean_price(price_el.get_text())

        # Description
        description = None
        desc_el = soup.select_one(".comment p, .adCommentsLanguage")
        if desc_el:
            description = desc_el.get_text(strip=True)

        # Features from info-features
        area_sqm = None
        rooms = None
        bathrooms = None
        floor = None

        for detail in soup.select(".info-features span, .details-property_features li"):
            text = detail.get_text(strip=True).lower()
            if "m²" in text or "mq" in text:
                area_sqm = clean_area(text)
            elif "local" in text or "stanz" in text:
                rooms = _safe_int(re.search(r"\d+", text))
            elif "bagn" in text:
                bathrooms = _safe_int(re.search(r"\d+", text))
            elif "piano" in text:
                floor_match = re.search(r"\d+", text)
                floor = floor_match.group() if floor_match else text

        # Images
        images = []
        for img in soup.select(".detail-image-gallery img, .gallery-container img"):
            src = img.get("data-src") or img.get("src", "")
            if src and "static" not in src:
                images.append(src)
        images = images[:20]

        # Energy class
        energy_class = None
        energy_el = soup.select_one(".icon-energy-rating-a, [class*='energy-certificate']")
        if energy_el:
            energy_text = energy_el.get_text(strip=True)
            ec_match = re.search(r"[A-G][+\d]*", energy_text, re.IGNORECASE)
            if ec_match:
                energy_class = ec_match.group().upper()

        # Features
        features_text = soup.get_text().lower()
        has_elevator = "ascensore" in features_text
        has_balcony = "balcone" in features_text
        has_terrace = "terrazzo" in features_text or "terrazza" in features_text
        has_garage = "garage" in features_text or "box auto" in features_text
        has_garden = "giardino" in features_text

        # Address
        address = None
        address_el = soup.select_one(".main-info__title-minor, .detail-info-address")
        if address_el:
            address = address_el.get_text(strip=True)

        # Listing type from URL
        listing_type = "rent" if "/affitto" in url else "sale"

        # City from breadcrumb or URL
        city_match = re.search(r"/(vendita|affitto)-case/([^/]+)/", url)
        city = city_match.group(2).replace("-", " ") if city_match else "unknown"

        return ListingItem(
            source_portal="idealista",
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=rooms,
            bathrooms=bathrooms,
            floor=floor,
            address=address,
            city=city,
            property_type="apartment",
            listing_type=listing_type,
            images=images,
            energy_class=energy_class,
            has_elevator=has_elevator,
            has_balcony=has_balcony,
            has_terrace=has_terrace,
            has_garage=has_garage,
            has_garden=has_garden,
            raw_data={},
        )


def _safe_int(match) -> int | None:
    if match is None:
        return None
    try:
        return int(match.group())
    except (ValueError, AttributeError):
        return None
