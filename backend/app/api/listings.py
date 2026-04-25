import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.listing import (
    ListingDetailResponse,
    ListingMarkersResponse,
    ListingResponse,
    ListingSearchParams,
    ListingSourceResponse,
    PaginatedListings,
)
from app.services.listing_service import (
    get_listing_detail,
    get_listing_markers,
    get_similar_listings,
    search_listings,
)

router = APIRouter(prefix="/api/listings", tags=["listings"])


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
        lat=lat, lng=lng, radius_km=radius_km, bbox=bbox,
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
        bbox=bbox,
    )
    return await get_listing_markers(db, params, limit=limit)


@router.get("/{listing_id}", response_model=ListingDetailResponse)
async def get_listing(listing_id: str, db: AsyncSession = Depends(get_db)) -> ListingDetailResponse:
    listing = await get_listing_detail(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    sources = [
        ListingSourceResponse(
            id=s.id,
            source_portal=s.source_portal,
            source_id=s.source_id,
            source_url=s.source_url,
            price_on_source=s.price_on_source,
            first_seen_at=s.first_seen_at,
            last_seen_at=s.last_seen_at,
            is_active=s.is_active,
        )
        for s in listing.sources
    ]

    return ListingDetailResponse(
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
        source_count=len(sources),
        sources=sources,
    )


@router.get("/{listing_id}/similar", response_model=list[ListingResponse])
async def similar_listings(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ListingResponse]:
    listing = await get_listing_detail(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    similar = await get_similar_listings(db, listing)
    return [
        ListingResponse(
            id=l.id, title=l.title, description=l.description,
            price=l.price, price_per_sqm=l.price_per_sqm, area_sqm=l.area_sqm,
            rooms=l.rooms, bedrooms=l.bedrooms, bathrooms=l.bathrooms,
            floor=l.floor, total_floors=l.total_floors,
            address=l.address, city=l.city, zone=l.zone, province=l.province,
            lat=l.lat, lng=l.lng,
            images=json.loads(l.images) if l.images else [],
            floor_plans=json.loads(l.floor_plans) if l.floor_plans else [],
            listing_url=l.listing_url, source_portal=l.source_portal, source_id=l.source_id,
            energy_class=l.energy_class, property_type=l.property_type,
            listing_type=l.listing_type, condition=l.condition, heating=l.heating,
            has_elevator=l.has_elevator, has_balcony=l.has_balcony,
            has_terrace=l.has_terrace, has_garage=l.has_garage, has_garden=l.has_garden,
            condominium_fees=l.condominium_fees, year_built=l.year_built,
            publication_date=l.publication_date,
            created_at=l.created_at, updated_at=l.updated_at,
            first_seen_at=l.first_seen_at, last_seen_at=l.last_seen_at,
            is_active=l.is_active, source_count=1,
        )
        for l in similar
    ]
