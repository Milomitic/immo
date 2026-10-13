import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Float)
    price_per_sqm: Mapped[float | None] = mapped_column(Float)
    area_sqm: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[int | None] = mapped_column(Integer)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[str | None] = mapped_column(Text)
    total_floors: Mapped[int | None] = mapped_column(Integer)

    # Location
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    zone: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    normalized_address: Mapped[str | None] = mapped_column(Text)

    # Media & links
    images: Mapped[str | None] = mapped_column(Text)  # JSON array
    floor_plans: Mapped[str | None] = mapped_column(Text)  # JSON array of planimetria image URLs
    listing_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_portal: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)

    # Classification
    energy_class: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str] = mapped_column(Text, nullable=False)  # apartment, house, villa...
    listing_type: Mapped[str] = mapped_column(Text, nullable=False)  # sale, rent
    condition: Mapped[str | None] = mapped_column(Text)
    heating: Mapped[str | None] = mapped_column(Text)

    # Features
    has_elevator: Mapped[bool | None] = mapped_column(Boolean)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean)
    has_terrace: Mapped[bool | None] = mapped_column(Boolean)
    has_garage: Mapped[bool | None] = mapped_column(Boolean)
    has_garden: Mapped[bool | None] = mapped_column(Boolean)

    # Price-change tracking. We re-check the listed price on every scrape
    # (cheap — read from the search-results page, no detail-page fetch).
    # If it differs from what's stored, ``price`` is rewritten to the new
    # value, ``price_previous`` keeps the prior value and
    # ``price_changed_at`` stamps the moment, so the UI can show
    # "ridotto" / "aumentato" badges.
    price_previous: Mapped[float | None] = mapped_column(Float)
    price_changed_at: Mapped[str | None] = mapped_column(Text)

    # Extra
    condominium_fees: Mapped[float | None] = mapped_column(Float)
    year_built: Mapped[int | None] = mapped_column(Integer)
    # Judicial / online auction rather than a normal sale (migration 0008).
    is_auction: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # The sale's data for auctions (date, base price, minimum offer, court,
    # links), as JSON; see app.schemas.listing.AuctionInfo.
    auction_info: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    publication_date: Mapped[str | None] = mapped_column(Text)  # Original date from source portal
    created_at: Mapped[str] = mapped_column(Text, default=_now)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)
    first_seen_at: Mapped[str] = mapped_column(Text, default=_now)
    last_seen_at: Mapped[str] = mapped_column(Text, default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    sources: Mapped[list["ListingSource"]] = relationship(back_populates="listing", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_listings_city_type", "city", "listing_type", "property_type"),
        Index("idx_listings_price", "price"),
        Index("idx_listings_source", "source_portal", "source_id", unique=True),
        Index("idx_listings_active", "is_active"),
        Index("idx_listings_location", "lat", "lng"),
        Index("idx_listings_normalized_addr", "normalized_address"),
    )


class ListingSource(Base):
    __tablename__ = "listing_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    listing_id: Mapped[str] = mapped_column(Text, ForeignKey("listings.id"), nullable=False)
    source_portal: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    price_on_source: Mapped[float | None] = mapped_column(Float)
    raw_data: Mapped[str | None] = mapped_column(Text)  # JSON
    first_seen_at: Mapped[str] = mapped_column(Text, default=_now)
    last_seen_at: Mapped[str] = mapped_column(Text, default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    listing: Mapped["Listing"] = relationship(back_populates="sources")

    __table_args__ = (
        Index("idx_sources_portal_id", "source_portal", "source_id", unique=True),
    )


class ListingPriceHistory(Base):
    """Append-only log of the prices shown for a listing.

    One row when the listing is first stored and one per later change
    (search-card diff, same-portal refresh, or a higher-priority portal
    taking over as canonical — ``source_portal`` says which). The
    ``price``/``price_previous`` columns on ``listings`` stay as the cheap
    "latest change" summary; this table is the full series for charts.
    """

    __tablename__ = "listing_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(
        Text, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source_portal: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[str] = mapped_column(Text, nullable=False, default=_now)

    __table_args__ = (
        Index("idx_price_history_listing", "listing_id", "observed_at"),
    )
