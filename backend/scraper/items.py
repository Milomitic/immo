from dataclasses import dataclass, field


@dataclass
class ListingItem:
    source_portal: str  # "immobiliare" | "idealista" | "casa"
    source_id: str
    source_url: str
    title: str
    city: str
    property_type: str  # apartment, house, villa, loft, studio, etc.
    listing_type: str  # "sale" | "rent"

    description: str | None = None
    price: float | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: str | None = None
    total_floors: int | None = None

    address: str | None = None
    zone: str | None = None
    province: str | None = None
    lat: float | None = None
    lng: float | None = None

    images: list[str] = field(default_factory=list)
    floor_plans: list[str] = field(default_factory=list)
    energy_class: str | None = None
    condition: str | None = None
    heating: str | None = None

    has_elevator: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_garage: bool | None = None
    has_garden: bool | None = None

    condominium_fees: float | None = None
    year_built: int | None = None
    publication_date: str | None = None  # ISO 8601 date from source portal

    raw_data: dict = field(default_factory=dict)
