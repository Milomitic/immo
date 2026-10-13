"""
Immobiliare.it spider.

Strategy: DataDome blocks /vendita-case/ but NOT /vendita-appartamenti/ and /affitto-case/.
All listing data is embedded in __NEXT_DATA__ JSON. Search pages cover price/area/rooms;
a fast parallel enrichment pass fills in publication_date from the lightweight
`/_next/data/{buildId}/annunci/{id}.json` endpoint for any item missing it inline.
"""

import asyncio
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams

# Enrichment hits a lightweight SSR JSON endpoint (not HTML), so we fan out far
# wider than the search-page concurrency. Tuned to saturate curl_cffi without
# drawing DataDome attention on a short burst.
_ENRICH_CONCURRENCY = 30
_ENRICH_TIMEOUT = 8.0


class ImmobiliareSpider(BaseSpider):
    portal_name = "immobiliare"
    base_url = "https://www.immobiliare.it"
    _build_id: str | None = None

    # Mapping listing_type -> URL paths that are NOT blocked by DataDome
    _PATHS = {
        "sale": [
            "/vendita-appartamenti/{city}/",  # apartments
            "/nuove-costruzioni/{city}/",     # new constructions
        ],
        "rent": [
            "/affitto-case/{city}/",
        ],
    }

    async def build_search_url(self, params: SearchParams, page: int) -> str:
        url = f"{self.base_url}{self._current_path}"
        if page > 1:
            url += f"?pag={page}"
        return url

    async def parse_search_results(self, html: str) -> list[str]:
        return []  # Not used — we extract directly from __NEXT_DATA__

    async def get_total_pages(self, html: str) -> int:
        data = self._parse_next_data(html)
        if not data:
            return 0
        return data.get("maxPages", 1)

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        return None  # Not used — we extract from search JSON

    async def run(self, params: SearchParams):
        """Extract listings from __NEXT_DATA__ JSON on search pages.
        All data comes from the search JSON — no per-listing detail fetch needed.
        """
        import structlog
        logger = structlog.get_logger()
        logger.info("spider_start", portal=self.portal_name, city=params.city)
        self.progress.set_phase("search")

        paths = self._PATHS.get(params.listing_type, self._PATHS["sale"])
        known_ids = params.known_source_ids or set()

        all_items: list = []
        # Search-page progress; each path's page count is only known once its
        # first page is in, so the total grows path by path.
        pages_total = 0
        for path_idx, path_template in enumerate(paths, start=1):
            self._current_path = path_template.format(city=params.city)
            logger.info("crawling_path", portal=self.portal_name, path=self._current_path)
            self.progress.set_description(
                f"path {path_idx}/{len(paths)} pag 1"
            )

            url = await self.build_search_url(params, page=1)
            html = await self.fetch(url, not_found_ok=False)
            data = self._parse_next_data(html) if html else None
            if not data:
                logger.warning("path_failed", portal=self.portal_name, path=self._current_path)
                self.search_pages_failed += 1
                if html:  # page served, payload gone: the layout changed
                    self.record_error("parse", url, None, "search payload (__NEXT_DATA__) not found")
                pages_total += 1
                self.progress.set_total(pages_total)
                self.progress.advance()
                continue

            site_pages = data.get("maxPages") or 1
            total_pages = min(site_pages, params.max_pages)
            if site_pages > params.max_pages:
                self.search_truncated = True
            pages_total += total_pages
            self.progress.set_total(pages_total)
            self.progress.advance()
            total_ads = data.get("totalAds", 0)
            logger.info("pages_found", portal=self.portal_name, path=self._current_path,
                        total_pages=total_pages, site_pages=site_pages, total_ads=total_ads)

            all_items.extend(self._extract_items(data, params))
            self.progress.set_description(
                f"path {path_idx}/{len(paths)} pag 1/{total_pages} ({len(all_items)} url)"
            )

            for page in range(2, total_pages + 1):
                if self.circuit_open:
                    self.search_pages_failed += total_pages - page + 1
                    break
                page_url = await self.build_search_url(params, page)
                page_html = await self.fetch(page_url, not_found_ok=False)
                self.progress.advance()
                page_data = self._parse_next_data(page_html) if page_html else None
                if not page_data:
                    self.search_pages_failed += 1
                    continue
                all_items.extend(self._extract_items(page_data, params))
                self.progress.set_description(
                    f"path {path_idx}/{len(paths)} pag {page}/{total_pages} ({len(all_items)} url)"
                )

        # The same listing can show up on two pages (results shift while we
        # paginate) or under both paths; keep the first occurrence.
        unique: dict[str, ListingItem] = {}
        for it in all_items:
            if it.source_id and it.source_id not in unique:
                unique[it.source_id] = it
        all_items = list(unique.values())
        self.listings_seen = len(all_items)

        # Skip listings that are already in the DB — first snapshot is
        # immutable, we only bump last_seen_at via the runner. The search
        # JSON also carries the *current* price for every result, so we
        # capture that for known listings too: the runner will diff it
        # against the stored price and mark changes — no detail-page
        # round-trip needed.
        to_yield = []
        for it in all_items:
            if it.source_id in known_ids:
                self.known_skipped_ids.append(it.source_id)
                if it.price is not None:
                    self.observed_prices[it.source_id] = it.price
            else:
                to_yield.append(it)

        if self.known_skipped_ids:
            logger.info("known_skipped", portal=self.portal_name,
                        count=len(self.known_skipped_ids), will_yield=len(to_yield))

        # Phase 2: parallel enrichment of publication_date for items missing
        # it. Updates the progress bar in-place.
        if to_yield:
            await self._enrich_all(to_yield)

        # Yield drained items — enrichment already populated publication_date
        # in place where possible.
        for item in to_yield:
            yield item

        self.progress.set_phase("done")
        logger.info("spider_done", portal=self.portal_name, total=len(to_yield))

    async def _enrich_all(self, items: list[ListingItem]) -> int:
        """Enrich items with data only the per-listing JSON exposes.

        Hits `/_next/data/{buildId}/annunci/{id}.json` — a lightweight SSR
        JSON endpoint, much cheaper than the HTML detail page. The search
        results don't carry ``publication_date`` for every item nor any
        floor plans (``multimedia.floorplans`` only appears in the per-
        listing payload), so we fan out one request per item missing
        either field. Bypasses the search-page rate limiter and fans out
        to _ENRICH_CONCURRENCY in-flight requests. Failures are swallowed:
        enrichment is best-effort.

        Returns how many items had at least one field populated.
        """
        import structlog
        logger = structlog.get_logger()

        # Enrich anything we don't already have. Items in `items` are
        # already filtered to the new (not-yet-known) ones by the caller,
        # so this is naturally bounded.
        pending = [
            it for it in items
            if it.source_id and (not it.publication_date or not it.floor_plans)
        ]
        if not pending or not self._build_id:
            return 0

        self.progress.set_phase("fetch")
        self.progress.set_total(len(pending))

        client = await self._get_client()
        sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)
        ok = 0

        async def one(item: ListingItem) -> None:
            nonlocal ok
            async with sem:
                try:
                    if await self._enrich_one(client, item):
                        ok += 1
                except Exception as e:
                    logger.debug("enrich_failed", source_id=item.source_id, error=str(e))
                finally:
                    self.progress.advance()

        await asyncio.gather(*(one(it) for it in pending))
        logger.info("enrich_done", portal=self.portal_name,
                    requested=len(pending), enriched=ok)
        return ok

    async def _enrich_one(self, client, item: ListingItem) -> bool:
        """Pull publication_date and floor plans off the per-listing JSON.

        Returns ``True`` if at least one field was populated, ``False``
        on any error (404, malformed JSON, missing fields).
        """
        url = f"{self.base_url}/_next/data/{self._build_id}/annunci/{item.source_id}.json"
        try:
            resp = await client.get(url, timeout=_ENRICH_TIMEOUT)
        except Exception:
            return False
        if resp.status_code != 200:
            return False
        try:
            data = resp.json()
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        re_data = (
            data.get("pageProps", {})
                .get("detailData", {})
                .get("realEstate", {})
        )
        if not isinstance(re_data, dict):
            return False

        touched = False

        # Publication date — search JSON sometimes carries it, sometimes
        # not. Detail JSON is more reliable.
        if not item.publication_date:
            created = re_data.get("createdAt") or re_data.get("dateAdded")
            iso = self._coerce_date(created)
            if iso:
                item.publication_date = iso
                touched = True

        # Floor plans live under ``properties[*].multimedia.floorplans``
        # with the same {urls: {large, medium, ...}} shape as photos.
        # Search JSON only carries ``photos``, not ``floorplans``.
        if not item.floor_plans:
            props = re_data.get("properties", []) or []
            main_prop = next((p for p in props if p.get("isMain")), None) or (props[0] if props else None)
            if main_prop:
                fps = (main_prop.get("multimedia") or {}).get("floorplans") or []
                plans: list[str] = []
                for fp in fps:
                    if not isinstance(fp, dict):
                        continue
                    urls = fp.get("urls") or {}
                    plan_url = urls.get("large") or urls.get("medium") or urls.get("small")
                    if plan_url:
                        # Same xxs-c→m-c upgrade we apply to photos for
                        # higher-quality output.
                        plan_url = plan_url.replace("/xxs-c.", "/m-c.")
                        plans.append(plan_url)
                if plans:
                    item.floor_plans = plans
                    touched = True

        return touched

    @staticmethod
    def _coerce_date(raw) -> str | None:
        """Convert epoch seconds / epoch millis / ISO string → 'YYYY-MM-DD'."""
        if raw is None:
            return None
        try:
            if isinstance(raw, bool):
                return None
            if isinstance(raw, (int, float)):
                ts = float(raw)
                if ts <= 0:
                    return None
                # Immobiliare uses epoch seconds, but tolerate millis too.
                if ts > 1e11:
                    ts /= 1000.0
                return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            if isinstance(raw, str):
                s = raw.strip()
                if not s:
                    return None
                # Already ISO-ish — trust the date prefix.
                if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                    return s[:10]
        except (ValueError, OSError, OverflowError):
            pass
        return None

    def _parse_next_data(self, html: str) -> dict | None:
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
            # Stash buildId on first successful parse — we need it to hit the
            # `/_next/data/{buildId}/...` JSON API during enrichment.
            if not self._build_id:
                bid = data.get("buildId")
                if isinstance(bid, str) and bid:
                    self._build_id = bid
            queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
            if queries:
                return queries[0].get("state", {}).get("data", {})
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
        return None

    def _extract_items(self, data: dict, params: SearchParams) -> list[ListingItem]:
        items = []
        results = data.get("results", [])

        for result in results:
            re_data = result.get("realEstate", {})
            if not re_data:
                continue

            listing_id = str(re_data.get("id", ""))
            seo_url = result.get("seo", {}).get("url", "")
            if not seo_url:
                seo_url = f"{self.base_url}/annunci/{listing_id}/"

            # Get main property (first one)
            properties = re_data.get("properties", [])
            main_prop = None
            for p in properties:
                if p.get("isMain"):
                    main_prop = p
                    break
            if not main_prop and properties:
                main_prop = properties[0]

            if not main_prop:
                continue

            # Location
            loc = main_prop.get("location", {})
            city = loc.get("city", params.city)
            address = loc.get("address", "")
            zone = loc.get("macrozone", "") or loc.get("microzone", "")
            province = loc.get("province", "")
            lat = loc.get("latitude")
            lng = loc.get("longitude")

            # Price
            price_data = main_prop.get("price", {})
            price = price_data.get("value")

            # Surface
            surface_str = main_prop.get("surface", "")
            area_sqm = self._parse_surface(surface_str)

            # Rooms & bathrooms
            rooms = self._parse_int(main_prop.get("rooms", ""))
            bathrooms = self._parse_int(main_prop.get("bathrooms", ""))
            bedrooms = self._parse_int(main_prop.get("bedRoomsNumber"))

            # Floor
            floor_data = main_prop.get("floor", {})
            floor = floor_data.get("abbreviation", "") if isinstance(floor_data, dict) else None

            # Condition & heating
            condition_raw = main_prop.get("ga4Condition", "")
            condition = self._map_condition(condition_raw) if condition_raw else None
            heating = main_prop.get("ga4Heating", None)

            # Elevator
            has_elevator = main_prop.get("elevator", None)

            # Features from ga4features
            ga4 = main_prop.get("ga4features", [])
            ga4_str = " ".join(ga4).lower() if ga4 else ""

            # Photos
            photos = main_prop.get("multimedia", {})
            if photos:
                photos = photos.get("photos", [])
            else:
                photos = []
            images = []
            for photo in photos[:15]:
                urls = photo.get("urls", {})
                img_url = urls.get("large") or urls.get("medium") or urls.get("small", "")
                if img_url:
                    img_url = img_url.replace("/xxs-c.", "/m-c.")
                    images.append(img_url)

            # Title
            title = main_prop.get("caption", "") or re_data.get("title", "")
            if not title:
                title = f"Appartamento in {'vendita' if params.listing_type == 'sale' else 'affitto'} a {city}"

            # Description
            description = main_prop.get("description", "")

            # Publication date — try inline first (often present in search
            # JSON), fall back to Phase-2 enrichment if missing.
            publication_date = self._coerce_date(
                re_data.get("createdAt")
                or re_data.get("dateAdded")
                or main_prop.get("createdAt")
            )

            # Typology
            typology = main_prop.get("typology", {})
            type_name = typology.get("name", "").lower() if isinstance(typology, dict) else ""
            property_type = self._map_property_type(type_name)

            # Energy class from description
            energy_class = None
            if description:
                # (?!…): "classe energetica esente" is no class E
                ec_match = re.search(r"classe\s+energetica\s*[:\s]*([A-G]\d?)(?![a-z])", description, re.IGNORECASE)
                if ec_match:
                    energy_class = ec_match.group(1).upper()

            items.append(ListingItem(
                source_portal="immobiliare",
                source_id=listing_id,
                source_url=seo_url,
                title=title,
                description=description[:2000] if description else None,
                price=price,
                area_sqm=area_sqm,
                rooms=rooms,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                floor=floor if floor else None,
                address=address,
                city=city.lower() if city else params.city,
                zone=zone,
                province=province,
                lat=lat,
                lng=lng,
                images=images,
                energy_class=energy_class,
                property_type=property_type,
                listing_type=params.listing_type,
                condition=condition,
                heating=heating,
                has_elevator=has_elevator,
                has_balcony="balcon" in ga4_str,
                has_terrace="terrazzo" in ga4_str or "terrazza" in ga4_str,
                has_garage="garage" in ga4_str or "box" in ga4_str,
                has_garden="giardino" in ga4_str,
                publication_date=publication_date,
                is_auction=re_data.get("contract") == "auction" or re_data.get("type") == "auction",
                raw_data={"realEstate_id": listing_id},
            ))

        return items

    @staticmethod
    def _parse_surface(s: str) -> float | None:
        if not s:
            return None
        match = re.search(r"([\d.,]+)", s.replace(".", "").replace(",", "."))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_int(s) -> int | None:
        if s is None:
            return None
        s = str(s)
        match = re.search(r"(\d+)", s)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _map_property_type(typology: str) -> str:
        mapping = {
            "appartamento": "apartment",
            "villa": "villa",
            "villetta": "house",
            "casa indipendente": "house",
            "loft": "loft",
            "attico": "apartment",
            "mansarda": "apartment",
            "monolocale": "studio",
            "rustico": "house",
            "casale": "house",
            "palazzo": "house",
            "progetto": "apartment",
        }
        for key, val in mapping.items():
            if key in typology:
                return val
        return "apartment"

    @staticmethod
    def _map_condition(raw: str) -> str | None:
        if not raw:
            return None
        lower = raw.lower()
        if "nuovo" in lower or "costruzione" in lower:
            return "nuovo"
        if "ristrutturato" in lower or "ottimo" in lower:
            return "ristrutturato"
        if "buono" in lower:
            return "buono"
        if "da ristrutturare" in lower or "ristrutturare" in lower:
            return "da_ristrutturare"
        if "abitabile" in lower or "discreto" in lower:
            return "buono"
        return raw.lower()
