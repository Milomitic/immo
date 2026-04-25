import json
import math

from sqlalchemy import cast, func, Integer as SAInteger, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.listing import Listing, ListingSource
from app.schemas.listing import (
    ListingMarker,
    ListingMarkersResponse,
    ListingResponse,
    ListingSearchParams,
    PaginatedListings,
)


def _listing_to_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        price_per_sqm=listing.price_per_sqm,
        area_sqm=listing.area_sqm,
        rooms=listing.rooms,
        bedrooms=listing.bedrooms,
        bathrooms=listing.bathrooms,
        floor=listing.floor,
        total_floors=listing.total_floors,
        address=listing.address,
        city=listing.city,
        zone=listing.zone,
        province=listing.province,
        lat=listing.lat,
        lng=listing.lng,
        images=json.loads(listing.images) if listing.images else [],
        floor_plans=json.loads(listing.floor_plans) if listing.floor_plans else [],
        listing_url=listing.listing_url,
        source_portal=listing.source_portal,
        source_id=listing.source_id,
        energy_class=listing.energy_class,
        property_type=listing.property_type,
        listing_type=listing.listing_type,
        condition=listing.condition,
        heating=listing.heating,
        has_elevator=listing.has_elevator,
        has_balcony=listing.has_balcony,
        has_terrace=listing.has_terrace,
        has_garage=listing.has_garage,
        has_garden=listing.has_garden,
        condominium_fees=listing.condominium_fees,
        year_built=listing.year_built,
        publication_date=listing.publication_date,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        is_active=listing.is_active,
        source_count=len(listing.sources) if listing.sources else 1,
    )


def _apply_listing_filters(query, params: ListingSearchParams):
    """Shared filter application for the paginated search and the map
    markers endpoint. Every WHERE clause derived from a search param lives
    here so both endpoints return consistent result sets.
    """
    query = query.where(Listing.is_active == True)

    # Full-text search via FTS5
    if params.q:
        # Use LIKE fallback since FTS5 virtual table requires raw SQL
        search_term = f"%{params.q}%"
        query = query.where(
            (Listing.title.ilike(search_term))
            | (Listing.description.ilike(search_term))
            | (Listing.address.ilike(search_term))
            | (Listing.city.ilike(search_term))
            | (Listing.zone.ilike(search_term))
        )

    if params.city:
        query = query.where(func.lower(Listing.city) == params.city.lower())
    if params.zone:
        zone_term = f"%{params.zone}%"
        query = query.where(
            (Listing.zone.ilike(zone_term))
            | (Listing.address.ilike(zone_term))
        )
    if params.province:
        query = query.where(func.lower(Listing.province) == params.province.lower())
    if params.listing_type:
        query = query.where(Listing.listing_type == params.listing_type)
    if params.property_type:
        query = query.where(Listing.property_type == params.property_type)
    if params.price_min is not None:
        query = query.where(Listing.price >= params.price_min)
    if params.price_max is not None:
        query = query.where(Listing.price <= params.price_max)
    if params.area_min is not None:
        query = query.where(Listing.area_sqm >= params.area_min)
    if params.area_max is not None:
        query = query.where(Listing.area_sqm <= params.area_max)
    if params.rooms_min is not None:
        query = query.where(Listing.rooms >= params.rooms_min)
    if params.rooms_max is not None:
        query = query.where(Listing.rooms <= params.rooms_max)
    if params.bedrooms_min is not None:
        query = query.where(Listing.bedrooms >= params.bedrooms_min)
    if params.bathrooms_min is not None:
        query = query.where(Listing.bathrooms >= params.bathrooms_min)
    if params.energy_class:
        query = query.where(Listing.energy_class == params.energy_class.upper())
    if params.has_elevator is not None:
        query = query.where(Listing.has_elevator == params.has_elevator)
    if params.has_balcony is not None:
        query = query.where(Listing.has_balcony == params.has_balcony)
    if params.has_terrace is not None:
        query = query.where(Listing.has_terrace == params.has_terrace)
    if params.has_garage is not None:
        query = query.where(Listing.has_garage == params.has_garage)
    if params.has_garden is not None:
        query = query.where(Listing.has_garden == params.has_garden)
    if params.condition:
        query = query.where(func.lower(Listing.condition) == params.condition.lower())
    if params.source_portal:
        query = query.where(Listing.source_portal == params.source_portal)
    if params.price_per_sqm_min is not None:
        query = query.where(Listing.price_per_sqm >= params.price_per_sqm_min)
    if params.price_per_sqm_max is not None:
        query = query.where(Listing.price_per_sqm <= params.price_per_sqm_max)
    if params.year_built_min is not None:
        query = query.where(Listing.year_built >= params.year_built_min)
    if params.year_built_max is not None:
        query = query.where(Listing.year_built <= params.year_built_max)

    # Floor filtering (floor is TEXT: "1","2","T","R","S", etc.)
    if params.floor_min is not None or params.floor_max is not None:
        floor_expr = "CAST(CASE " \
                     "WHEN listings.floor GLOB '[0-9]*' THEN listings.floor " \
                     "WHEN listings.floor = 'T' THEN '0' " \
                     "WHEN listings.floor = 'R' THEN '0' " \
                     "ELSE NULL END AS INTEGER)"
        query = query.where(Listing.floor.isnot(None))
        if params.floor_min is not None:
            query = query.where(text(f"{floor_expr} >= :floor_min").bindparams(floor_min=params.floor_min))
        if params.floor_max is not None:
            query = query.where(text(f"{floor_expr} <= :floor_max").bindparams(floor_max=params.floor_max))

    # Geo filtering (radius around a point)
    if params.lat is not None and params.lng is not None and params.radius_km is not None:
        lat_delta = params.radius_km / 111.0
        lng_delta = params.radius_km / (111.0 * math.cos(math.radians(params.lat)))
        query = query.where(
            Listing.lat.between(params.lat - lat_delta, params.lat + lat_delta),
            Listing.lng.between(params.lng - lng_delta, params.lng + lng_delta),
        )

    # Map viewport filtering. bbox arrives as "south,west,north,east".
    # We drop listings without coordinates since they can't be placed on a map.
    if params.bbox:
        try:
            south, west, north, east = (float(x) for x in params.bbox.split(","))
        except (ValueError, AttributeError):
            south = west = north = east = None  # type: ignore[assignment]
        if south is not None:
            query = query.where(
                Listing.lat.isnot(None),
                Listing.lng.isnot(None),
                Listing.lat.between(south, north),
                Listing.lng.between(west, east),
            )

    return query


async def search_listings(db: AsyncSession, params: ListingSearchParams) -> PaginatedListings:
    query = select(Listing).options(selectinload(Listing.sources))
    query = _apply_listing_filters(query, params)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort. "newest" uses the original publication_date from the source
    # portal (what the user actually cares about), falling back to
    # first_seen_at only when the portal didn't expose a date.
    newest_order = func.coalesce(Listing.publication_date, Listing.first_seen_at).desc()
    sort_map = {
        "newest": newest_order,
        "price_asc": Listing.price.asc().nulls_last(),
        "price_desc": Listing.price.desc().nulls_last(),
        "area_desc": Listing.area_sqm.desc().nulls_last(),
        "price_sqm_asc": Listing.price_per_sqm.asc().nulls_last(),
        "price_sqm_desc": Listing.price_per_sqm.desc().nulls_last(),
    }
    order = sort_map.get(params.sort, newest_order)
    query = query.order_by(order)

    # Pagination
    offset = (params.page - 1) * params.page_size
    query = query.offset(offset).limit(params.page_size)

    result = await db.execute(query)
    listings = result.scalars().unique().all()

    return PaginatedListings(
        items=[_listing_to_response(l) for l in listings],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 0,
    )


_MAP_MARKERS_HARD_LIMIT = 2000


async def get_listing_markers(
    db: AsyncSession,
    params: ListingSearchParams,
    limit: int = _MAP_MARKERS_HARD_LIMIT,
) -> ListingMarkersResponse:
    """Lightweight projection for the map view. Returns up to `limit`
    geocoded listings inside the current viewport/filters — just the
    fields a pin + popup needs."""
    limit = min(limit, _MAP_MARKERS_HARD_LIMIT)

    query = select(
        Listing.id,
        Listing.lat,
        Listing.lng,
        Listing.price,
        Listing.title,
        Listing.property_type,
        Listing.listing_type,
        Listing.city,
        Listing.zone,
        Listing.area_sqm,
        Listing.rooms,
        Listing.images,
    ).where(Listing.lat.isnot(None), Listing.lng.isnot(None))
    query = _apply_listing_filters(query, params)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Newest first so that if we hit the cap the user still sees fresh inventory.
    query = query.order_by(
        func.coalesce(Listing.publication_date, Listing.first_seen_at).desc()
    ).limit(limit + 1)

    rows = (await db.execute(query)).all()
    truncated = len(rows) > limit
    rows = rows[:limit]

    markers: list[ListingMarker] = []
    for row in rows:
        images_raw = row.images
        thumbnail = None
        if images_raw:
            try:
                parsed = json.loads(images_raw)
                if isinstance(parsed, list) and parsed:
                    thumbnail = parsed[0]
            except (json.JSONDecodeError, ValueError):
                pass
        markers.append(
            ListingMarker(
                id=row.id,
                lat=row.lat,
                lng=row.lng,
                price=row.price,
                title=row.title,
                property_type=row.property_type,
                listing_type=row.listing_type,
                city=row.city,
                zone=row.zone,
                area_sqm=row.area_sqm,
                rooms=row.rooms,
                thumbnail=thumbnail,
            )
        )

    return ListingMarkersResponse(markers=markers, total=total, truncated=truncated)


async def get_listing_detail(db: AsyncSession, listing_id: str) -> Listing | None:
    result = await db.execute(
        select(Listing).options(selectinload(Listing.sources)).where(Listing.id == listing_id)
    )
    return result.scalar_one_or_none()


async def get_similar_listings(db: AsyncSession, listing: Listing, limit: int = 6) -> list[Listing]:
    query = (
        select(Listing)
        .where(
            Listing.id != listing.id,
            Listing.is_active == True,
            Listing.city == listing.city,
            Listing.listing_type == listing.listing_type,
            Listing.property_type == listing.property_type,
        )
    )

    if listing.price:
        price_range = listing.price * 0.2
        query = query.where(
            Listing.price.between(listing.price - price_range, listing.price + price_range)
        )

    query = query.order_by(Listing.first_seen_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
