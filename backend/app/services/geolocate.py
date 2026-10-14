"""Map positions for listings the portals don't place, from their street.

Subito publishes no coordinates, some agencies hide them (Wikicasa,
Vistocasa, RE/MAX): those listings would never appear on the map. A listing
that names its street gets a pin there, and how it was found is recorded
(``listings.geo_precision``) so the map can mark the pin as approximate and
deduplication never mistakes it for a real location:

* ``address`` — street and house number;
* ``street``  — the street without a number: its middle.

A neighbourhood or a town alone is too vague for a pin: such listings stay
off the map (they're still in the lists).

The street comes from the address, from a zone field that holds one
("Via Virgilio"), or from the title and description ("Bari – San Pasquale
Alta, Via Fanelli"). Its position is first taken from our own data — the
median of the listings placed exactly on that street — and otherwise asked
of OpenStreetMap's Nominatim, within its usage policy: one request per
second, an identifying User-Agent, every answer cached in
``geocode_cache`` (misses too), so each street is looked up once, ever.
"""

import asyncio
import json
import math
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models.geocode import GeocodeCache
from app.models.listing import Listing

logger = structlog.get_logger()

PRECISIONS = ("address", "street")
# A point further than this from the town's centre is a different place
# with the same street name.
MAX_KM_FROM_CITY = 25
# Our own data counts once this many exact listings agree on a street; a
# town needs more to have a reliable centre.
MIN_STREET_POINTS = 2
MIN_CITY_POINTS = 5

_STREET_TYPES = (
    "via", "viale", "corso", "piazza", "piazzale", "largo", "strada", "lungomare",
    "vico", "vicolo", "traversa", "contrada", "salita", "rione", "borgo",
)
_TYPE_RE = re.compile(rf"^({'|'.join(_STREET_TYPES)})\b\s*", re.IGNORECASE)
# Every "via …" in a text, overlapping ones included ("via Garruba ad
# altezza di via De Rossi" names two streets).
_TEXT_STREET_RE = re.compile(
    rf"(?=\b({'|'.join(_STREET_TYPES)})\.?\s+([^\n\r,.;:()/|\-–—\d]{{2,60}}))", re.IGNORECASE
)
# Words that end a street name in running text ("via Garruba ad altezza
# di…", "corso Umberto I che dalla stazione…").
_STOP_WORDS = {
    "a", "ad", "al", "alla", "alle", "all", "in", "con", "e", "ed", "che", "dove", "zona",
    "nei", "nel", "nella", "nelle", "dal", "dalla", "pressi", "vicino", "vicinanze", "angolo",
    "ang", "altezza", "n", "nr", "civico", "piano", "primo", "secondo", "terzo", "quarto",
    "int", "interno", "presso", "tra", "fra", "per", "appartamento", "trilocale", "bilocale",
    "quadrilocale", "vendesi", "vendo", "affittasi", "ottimo", "ottima", "ampio", "ampia",
    "luminoso", "luminosa", "the", "of",
}
_HOUSE_NUMBER_RE = re.compile(r"\b(\d{1,4})\s*([a-zA-Z]|bis)?\s*$")
_QUOTES_RE = re.compile(r"['’`\"]{2,}|[\"“”«»]")

_STREET_CATEGORIES = {"highway"}
_HOUSE_TYPES = {"house", "building", "residential", "apartments", "yes"}


@dataclass(frozen=True)
class Place:
    lat: float
    lng: float
    precision: str


def _norm(text: str | None) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\bs\.\s*", "san ", text)  # "S. Pasquale" → "san pasquale"
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _bare(street_key: str) -> str:
    """Street key without its type word: "via giulio petroni" → "giulio petroni"."""
    return _TYPE_RE.sub("", street_key).strip()


def _street_words(words: list[str]) -> list[str]:
    """A street name's words: up to the first word that ends it, at most 5."""
    kept: list[str] = []
    for word in words:
        if word.lower().strip("'’") in _STOP_WORDS:
            break
        kept.append(word)
        if len(kept) == 5:
            break
    return kept


def split_address(address: str | None) -> tuple[str | None, str | None]:
    """("Via Amendola", "126") from "Via Amendola, 126" / "via Amendola 126";
    (None, None) when the text names no street."""
    address = _QUOTES_RE.sub(" ", address or "")
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return None, None
    street = parts[0]
    number = None
    m = _HOUSE_NUMBER_RE.search(street)
    if m and _TYPE_RE.match(street):
        number = m.group(1)
        street = street[: m.start()].strip()
    if number is None:
        for part in parts[1:]:
            if re.fullmatch(r"\d{1,4}\s*[a-zA-Z]?", part):
                number = re.match(r"\d+", part).group(0)
                break
    type_match = _TYPE_RE.match(street)
    if not type_match or not _bare(_norm(street)):
        return None, None  # "Zona Poggiofranco", "Trattativa riservata"…
    words = _street_words(street[type_match.end():].split())
    if not words:
        return None, None
    return f"{type_match.group(1)} {' '.join(words)}", number


def streets_in_text(text: str | None) -> list[str]:
    """Street names mentioned in free text, in order of appearance."""
    found: list[str] = []
    for m in _TEXT_STREET_RE.finditer(_QUOTES_RE.sub(" ", text or "")):
        words = _street_words(m.group(2).split())
        if words:
            name = f"{m.group(1).capitalize()} {' '.join(words)}"
            if name not in found:
                found.append(name)
    return found


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def _median(points: list[tuple[float, float]]) -> tuple[float, float]:
    return statistics.median(p[0] for p in points), statistics.median(p[1] for p in points)


class LocalIndex:
    """Where our own exactly-placed listings are, by street and by town."""

    def __init__(self, rows):
        self.streets: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
        self.bare: dict[tuple[str, str], set[str]] = defaultdict(set)  # last word → street keys
        self.addresses: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
        self.cities: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for city, address, lat, lng in rows:
            city = _norm(city)
            point = (lat, lng)
            self.cities[city].append(point)
            street, number = split_address(address)
            if street:
                key = _norm(street)
                self.streets[(city, key)].append(point)
                self.bare[(city, _bare(key).split()[-1])].add(key)
                if number:
                    self.addresses[(city, f"{key} {number}")].append(point)

    def city_centre(self, city: str) -> tuple[float, float] | None:
        points = self.cities.get(_norm(city)) or []
        return _median(points) if len(points) >= MIN_CITY_POINTS else None

    def address(self, city: str, street: str, number: str) -> tuple[float, float] | None:
        points = self.addresses.get((_norm(city), f"{_norm(street)} {number}")) or []
        return _median(points) if points else None

    def street(self, city: str, street: str) -> tuple[float, float] | None:
        city, key = _norm(city), _norm(street)
        points = self.streets.get((city, key))
        if not points:
            # "Via Fanelli" for "via giuseppe fanelli": accepted when only
            # one known street of the town ends with that name.
            bare = _bare(key)
            candidates = [k for k in self.bare.get((city, bare.split()[-1] if bare else ""), set())
                          if _bare(k).endswith(bare)] if bare else []
            if len(candidates) == 1:
                points = self.streets[(city, candidates[0])]
        return _median(points) if points and len(points) >= MIN_STREET_POINTS else None


class Nominatim:
    """OpenStreetMap's geocoder, used as its policy asks: at most one
    request per second, an identifying User-Agent, results cached."""

    URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "Immo/0.1 (personal real-estate aggregator; +https://github.com/Milomitic/immo)"
    MIN_INTERVAL = 1.1

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": self.USER_AGENT})
        self._last = 0.0
        self.requests = 0

    async def close(self) -> None:
        await self.client.aclose()

    async def search(self, query: str) -> dict | None:
        """First hit for a free-form query, restricted to Italy, or None."""
        key = query.strip().lower()
        # Short sessions only: the network wait must never hold SQLite's
        # write lock (the scraper and the API write meanwhile).
        async with async_session() as db:
            cached = await db.get(GeocodeCache, key)
        if cached is not None:
            return json.loads(cached.result) if cached.result else None

        wait = self.MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        try:
            resp = await self.client.get(
                self.URL,
                params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "it"},
                headers={"User-Agent": self.USER_AGENT},
            )
            resp.raise_for_status()
            hits = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("geocode_failed", query=query, error=str(e))
            return None  # not cached: worth retrying next time
        hit = hits[0] if isinstance(hits, list) and hits else None
        result = None
        if hit:
            result = {"lat": float(hit["lat"]), "lng": float(hit["lon"]),
                      "category": hit.get("category"), "type": hit.get("type")}
        async with async_session() as db:
            await db.merge(GeocodeCache(query=key, result=json.dumps(result) if result else None,
                                        created_at=datetime.now(timezone.utc).isoformat()))
            await db.commit()
        return result


class Locator:
    def __init__(self, index: LocalIndex, geocoder: Nominatim | None):
        self.index = index
        self.geocoder = geocoder

    async def _ask(self, query: str, near: tuple[float, float] | None, accept) -> tuple[float, float] | None:
        """Nominatim's answer, if accepted and plausibly in this town."""
        if self.geocoder is None:
            return None
        hit = await self.geocoder.search(query)
        if not hit or not accept(hit):
            return None
        point = (hit["lat"], hit["lng"])
        if near and _distance_km(point, near) > MAX_KM_FROM_CITY:
            return None
        return point

    async def city_centre(self, city: str) -> tuple[float, float] | None:
        """Only a reference, to reject a homonymous street elsewhere."""
        return self.index.city_centre(city) or await self._ask(
            f"{city}, Italia", None, lambda h: h.get("category") in ("place", "boundary")
        )

    async def street(self, city: str, street: str, number: str | None, near) -> Place | None:
        if number:
            point = self.index.address(city, street, number) or await self._ask(
                f"{street} {number}, {city}", near,
                lambda h: h.get("type") in _HOUSE_TYPES or h.get("category") == "place",
            )
            if point:
                return Place(*point, "address")
        point = self.index.street(city, street) or await self._ask(
            f"{street}, {city}", near, lambda h: h.get("category") in _STREET_CATEGORIES
        )
        return Place(*point, "street") if point else None

    async def locate(self, city: str, address: str | None, zone: str | None,
                     title: str | None, description: str | None) -> Place | None:
        if not city:
            return None
        near = await self.city_centre(city)

        # The address; then the zone field, which some portals fill with a
        # street ("Via Virgilio")…
        for field in (address, zone):
            street, number = split_address(field)
            if street:
                place = await self.street(city, street, number, near)
                if place:
                    return place
        # …or with a street name alone ("Cesare Battisti"): good if it is one.
        if zone and not split_address(zone)[0]:
            point = await self._ask(f"{zone.strip()}, {city}", near,
                                    lambda h: h.get("category") in _STREET_CATEGORIES)
            if point:
                return Place(*point, "street")

        # Nothing structured (Subito): the streets the ad's text names.
        for street_name in streets_in_text(f"{title or ''}\n{description or ''}")[:3]:
            place = await self.street(city, street_name, None, near)
            if place:
                return place
        return None  # a zone or a town alone: no pin


async def locate_missing_listings(
    *, use_network: bool | None = None, limit: int | None = None, geocoder: Nominatim | None = None
) -> dict[str, int]:
    """Place every active listing without coordinates that names its street.
    Unplaced ones are retried at each run: cached lookups make that cheap,
    and a later run may know the street. Returns how many got each
    precision, plus "none"."""
    if use_network is None:
        use_network = settings.GEOCODER_ENABLED
    async with async_session() as db:
        # Estimates coarser than a street (an earlier version made zone and
        # town ones) don't belong on the map.
        await db.execute(
            update(Listing).where(Listing.geo_precision.is_not(None), Listing.geo_precision.not_in(PRECISIONS))
            .values(lat=None, lng=None, geo_precision=None)
        )
        await db.commit()
        exact = (await db.execute(
            select(Listing.city, Listing.address, Listing.lat, Listing.lng).where(
                Listing.lat.is_not(None), Listing.lng.is_not(None), Listing.geo_precision.is_(None)
            )
        )).all()
        query = select(Listing.id, Listing.city, Listing.address, Listing.zone, Listing.title,
                       Listing.description).where(Listing.is_active.is_(True), Listing.lat.is_(None))
        if limit:
            query = query.limit(limit)
        missing = (await db.execute(query)).all()
    if not missing:
        return {}

    own_geocoder = geocoder is None and use_network
    if own_geocoder:
        geocoder = Nominatim()
    locator = Locator(LocalIndex(exact), geocoder if use_network else None)
    counts: dict[str, int] = defaultdict(int)
    pending: list[tuple[str, Place]] = []

    async def write() -> None:
        async with async_session() as db:
            for listing_id, place in pending:
                await db.execute(
                    # lat IS NULL: not if a portal has placed it meanwhile
                    update(Listing).where(Listing.id == listing_id, Listing.lat.is_(None))
                    .values(lat=place.lat, lng=place.lng, geo_precision=place.precision)
                )
            await db.commit()
        pending.clear()

    try:
        for row in missing:
            place = await locator.locate(row.city, row.address, row.zone, row.title, row.description)
            if place is None:
                counts["none"] += 1
                continue
            counts[place.precision] += 1
            pending.append((row.id, place))
            if len(pending) >= 50:
                await write()
        if pending:
            await write()
    finally:
        if own_geocoder:
            logger.info("geocoder_requests", count=geocoder.requests)
            await geocoder.close()
    logger.info("listings_located", **counts)
    return dict(counts)
