from pydantic import BaseModel, Field


class ListingBase(BaseModel):
    title: str
    description: str | None = None
    price: float | None = None
    price_previous: float | None = None
    price_changed_at: str | None = None
    price_per_sqm: float | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: str | None = None
    total_floors: int | None = None
    address: str | None = None
    city: str
    zone: str | None = None
    province: str | None = None
    lat: float | None = None
    lng: float | None = None
    images: list[str] = []
    floor_plans: list[str] = []
    listing_url: str
    source_portal: str
    source_id: str
    energy_class: str | None = None
    property_type: str
    listing_type: str
    condition: str | None = None
    heating: str | None = None
    has_elevator: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_garage: bool | None = None
    has_garden: bool | None = None
    condominium_fees: float | None = None
    year_built: int | None = None


class ListingResponse(ListingBase):
    id: str
    publication_date: str | None = None
    created_at: str
    updated_at: str
    first_seen_at: str
    last_seen_at: str
    is_active: bool
    source_count: int = 1

    model_config = {"from_attributes": True}


class ListingSourceResponse(BaseModel):
    id: str
    source_portal: str
    source_id: str
    source_url: str
    price_on_source: float | None = None
    first_seen_at: str
    last_seen_at: str
    is_active: bool

    model_config = {"from_attributes": True}


class ListingDetailResponse(ListingResponse):
    sources: list[ListingSourceResponse] = []


class PricePointResponse(BaseModel):
    price: float
    observed_at: str
    source_portal: str | None = None

    model_config = {"from_attributes": True}


class ListingSearchParams(BaseModel):
    q: str | None = None
    city: str | None = None
    zone: str | None = None
    province: str | None = None
    listing_type: str | None = None
    property_type: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    rooms_min: int | None = None
    rooms_max: int | None = None
    bedrooms_min: int | None = None
    bathrooms_min: int | None = None
    energy_class: str | None = None
    condition: str | None = None
    source_portal: str | None = None
    has_elevator: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_garage: bool | None = None
    has_garden: bool | None = None
    floor_min: int | None = None
    floor_max: int | None = None
    price_per_sqm_min: float | None = None
    price_per_sqm_max: float | None = None
    year_built_min: int | None = None
    year_built_max: int | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None
    bbox: str | None = None  # "south,west,north,east" — used by the map view
    # Free-form polygon as ``"lat1,lng1;lat2,lng2;...;latN,lngN"``. Ring is
    # auto-closed if the last vertex differs from the first. Applied as a
    # bounding-box pre-filter in SQL plus a point-in-polygon refinement in
    # Python — see services.listing_service.
    polygon: str | None = None
    sort: str = "newest"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedListings(BaseModel):
    items: list[ListingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ListingMarker(BaseModel):
    """Slim projection of a listing for map markers — just what a pin needs."""

    id: str
    lat: float
    lng: float
    price: float | None = None
    title: str
    property_type: str
    listing_type: str
    city: str
    zone: str | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    thumbnail: str | None = None

    model_config = {"from_attributes": True}


class ListingMarkersResponse(BaseModel):
    markers: list[ListingMarker]
    total: int
    truncated: bool  # true when we hit `limit` and more results exist
