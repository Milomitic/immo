import math

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.utils.text import normalize_address


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in meters between two lat/lng points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_similarity(
    address_a: str | None,
    price_a: float | None,
    area_a: float | None,
    rooms_a: int | None,
    lat_a: float | None,
    lng_a: float | None,
    address_b: str | None,
    price_b: float | None,
    area_b: float | None,
    rooms_b: int | None,
    lat_b: float | None,
    lng_b: float | None,
) -> float:
    score = 0.0
    weights_total = 0.0

    # Address similarity (weight: 0.35)
    if address_a and address_b:
        addr_sim = fuzz.token_sort_ratio(address_a, address_b) / 100.0
        score += 0.35 * addr_sim
        weights_total += 0.35

    # Price similarity (weight: 0.20)
    if price_a and price_b:
        price_diff = abs(price_a - price_b) / max(price_a, price_b)
        price_sim = max(0, 1.0 - price_diff / 0.10)
        score += 0.20 * price_sim
        weights_total += 0.20

    # Area similarity (weight: 0.20)
    if area_a and area_b:
        area_diff = abs(area_a - area_b) / max(area_a, area_b)
        area_sim = max(0, 1.0 - area_diff / 0.10)
        score += 0.20 * area_sim
        weights_total += 0.20

    # Rooms match (weight: 0.10)
    if rooms_a is not None and rooms_b is not None:
        rooms_sim = 1.0 if rooms_a == rooms_b else 0.0
        score += 0.10 * rooms_sim
        weights_total += 0.10

    # Geo proximity (weight: 0.15)
    if all(v is not None for v in [lat_a, lng_a, lat_b, lng_b]):
        distance = haversine(lat_a, lng_a, lat_b, lng_b)
        geo_sim = max(0, 1.0 - distance / 200.0)
        score += 0.15 * geo_sim
        weights_total += 0.15

    return score / weights_total if weights_total > 0 else 0.0


async def find_duplicate(
    db: AsyncSession,
    city: str,
    listing_type: str,
    property_type: str,
    address: str | None,
    price: float | None,
    area_sqm: float | None,
    rooms: int | None,
    lat: float | None,
    lng: float | None,
    exclude_portal: str | None = None,
    threshold: float = 0.85,
) -> Listing | None:
    """Find a near-duplicate listing in the DB."""
    normalized_addr = normalize_address(address, city)

    query = select(Listing).where(
        Listing.city == city.lower(),
        Listing.listing_type == listing_type,
        Listing.property_type == property_type,
        Listing.is_active == True,
    )

    if exclude_portal:
        query = query.where(Listing.source_portal != exclude_portal)

    # Narrow candidates by price range if available
    if price:
        query = query.where(
            Listing.price.between(price * 0.85, price * 1.15)
        )

    result = await db.execute(query)
    candidates = result.scalars().all()

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        score = compute_similarity(
            normalized_addr, price, area_sqm, rooms, lat, lng,
            candidate.normalized_address, candidate.price, candidate.area_sqm,
            candidate.rooms, candidate.lat, candidate.lng,
        )
        if score >= threshold and score > best_score:
            best_score = score
            best_match = candidate

    return best_match
