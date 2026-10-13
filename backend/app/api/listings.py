from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.listing import Listing
from app.schemas.listing import (
    ListingDetailResponse,
    ListingMarkersResponse,
    ListingResponse,
    ListingSearchParams,
    ListingSourceResponse,
    PaginatedListings,
    PricePointResponse,
)
from app.services.listing_service import (
    get_listing_detail,
    get_listing_markers,
    get_price_history,
    get_similar_listings,
    listing_to_response,
    search_listings,
)

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("", response_model=PaginatedListings)
async def list_listings(
    q: str | None = None,
    city: str | None = None,
    zone: str | None = None,
    province: str | None = None,
    listing_type: str | None = None,
    property_type: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    area_min: float | None = None,
    area_max: float | None = None,
    rooms_min: int | None = None,
    rooms_max: int | None = None,
    bedrooms_min: int | None = None,
    bathrooms_min: int | None = None,
    energy_class: str | None = None,
    condition: str | None = None,
    source_portal: str | None = None,
    has_elevator: bool | None = None,
    has_balcony: bool | None = None,
    has_terrace: bool | None = None,
    has_garage: bool | None = None,
    has_garden: bool | None = None,
    floor_min: int | None = None,
    floor_max: int | None = None,
    price_per_sqm_min: float | None = None,
    price_per_sqm_max: float | None = None,
    year_built_min: int | None = None,
    year_built_max: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
    first_seen_after: str | None = None,
    price_drop_since: str | None = None,
    sort: str = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedListings:
    params = ListingSearchParams(
        q=q, city=city, zone=zone, province=province,
        listing_type=listing_type, property_type=property_type,
        price_min=price_min, price_max=price_max,
        area_min=area_min, area_max=area_max,
        rooms_min=rooms_min, rooms_max=rooms_max,
        bedrooms_min=bedrooms_min, bathrooms_min=bathrooms_min,
        energy_class=energy_class, condition=condition, source_portal=source_portal,
        has_elevator=has_elevator, has_balcony=has_balcony,
        has_terrace=has_terrace, has_garage=has_garage, has_garden=has_garden,
        floor_min=floor_min, floor_max=floor_max,
        price_per_sqm_min=price_per_sqm_min, price_per_sqm_max=price_per_sqm_max,
        year_built_min=year_built_min, year_built_max=year_built_max,
        lat=lat, lng=lng, radius_km=radius_km, bbox=bbox, polygon=polygon,
        first_seen_after=first_seen_after, price_drop_since=price_drop_since,
        sort=sort, page=page, page_size=page_size,
    )
    return await search_listings(db, params)


@router.get("/map", response_model=ListingMarkersResponse)
async def list_listing_markers(
    q: str | None = None,
    city: str | None = None,
    zone: str | None = None,
    province: str | None = None,
    listing_type: str | None = None,
    property_type: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    area_min: float | None = None,
    area_max: float | None = None,
    rooms_min: int | None = None,
    rooms_max: int | None = None,
    bedrooms_min: int | None = None,
    bathrooms_min: int | None = None,
    energy_class: str | None = None,
    condition: str | None = None,
    source_portal: str | None = None,
    has_elevator: bool | None = None,
    has_balcony: bool | None = None,
    has_terrace: bool | None = None,
    has_garage: bool | None = None,
    has_garden: bool | None = None,
    floor_min: int | None = None,
    floor_max: int | None = None,
    price_per_sqm_min: float | None = None,
    price_per_sqm_max: float | None = None,
    year_built_min: int | None = None,
    year_built_max: int | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
    first_seen_after: str | None = None,
    price_drop_since: str | None = None,
    limit: int = Query(default=2000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> ListingMarkersResponse:
    params = ListingSearchParams(
        q=q, city=city, zone=zone, province=province,
        listing_type=listing_type, property_type=property_type,
        price_min=price_min, price_max=price_max,
        area_min=area_min, area_max=area_max,
        rooms_min=rooms_min, rooms_max=rooms_max,
        bedrooms_min=bedrooms_min, bathrooms_min=bathrooms_min,
        energy_class=energy_class, condition=condition, source_portal=source_portal,
        has_elevator=has_elevator, has_balcony=has_balcony,
        has_terrace=has_terrace, has_garage=has_garage, has_garden=has_garden,
        floor_min=floor_min, floor_max=floor_max,
        price_per_sqm_min=price_per_sqm_min, price_per_sqm_max=price_per_sqm_max,
        year_built_min=year_built_min, year_built_max=year_built_max,
        bbox=bbox, polygon=polygon,
        first_seen_after=first_seen_after, price_drop_since=price_drop_since,
    )
    return await get_listing_markers(db, params, limit=limit)


@router.get("/{listing_id}", response_model=ListingDetailResponse)
async def get_listing(listing_id: str, db: AsyncSession = Depends(get_db)) -> ListingDetailResponse:
    listing = await get_listing_detail(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    sources = [ListingSourceResponse.model_validate(s) for s in listing.sources]
    base = listing_to_response(listing)
    return ListingDetailResponse(**base.model_dump(), sources=sources)


@router.get("/{listing_id}/similar", response_model=list[ListingResponse])
async def similar_listings(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ListingResponse]:
    listing = await get_listing_detail(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    similar = await get_similar_listings(db, listing)
    return [listing_to_response(s) for s in similar]


@router.get("/{listing_id}/price-history", response_model=list[PricePointResponse])
async def price_history(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[PricePointResponse]:
    if await db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return [PricePointResponse.model_validate(p) for p in await get_price_history(db, listing_id)]
