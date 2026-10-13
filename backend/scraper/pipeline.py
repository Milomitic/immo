import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.listing import Listing, ListingPriceHistory, ListingSource
from app.services.dedup_service import find_duplicate
from app.utils.text import normalize_address
from scraper.items import ListingItem
from scraper.utils.html_extract import clamp_italy_coords, clamp_publication_date, detect_auction

logger = structlog.get_logger()

# Portal priority for deduplication: lower index = higher priority.
# When duplicates exist, the highest-priority portal becomes the canonical listing.
PORTAL_PRIORITY = ["immobiliare", "casa", "tecnocasa", "gabetti", "remax", "vistocasa", "idealista"]


async def get_known_source_ids(portal: str) -> set[str]:
    """Return *every* source_id we've ever recorded for ``portal`` —
    canonical listings plus secondary sources (when this portal's listing
    attached as a duplicate to a higher-priority canonical).

    Used by spiders to skip the detail-page fetch on listings that are
    already in the DB. Was previously time-windowed (``fresh_hours``) but
    that meant every 6 hours we re-fetched everything and overwrote the
    original snapshot via ``_update_listing``. We now treat the first
    observation as immutable: once a listing is in the DB, subsequent
    runs only bump its ``last_seen_at`` (so the
    ``LISTING_INACTIVE_DAYS`` deactivation logic still works).
    """
    known: set[str] = set()
    async with async_session() as db:
        rows = await db.execute(
            select(Listing.source_id).where(Listing.source_portal == portal)
        )
        known.update(r[0] for r in rows if r[0])
        src_rows = await db.execute(
            select(ListingSource.source_id).where(ListingSource.source_portal == portal)
        )
        known.update(r[0] for r in src_rows if r[0])
    return known


async def update_prices_from_observations(
    portal: str,
    observed: dict[str, float],
) -> dict[str, int]:
    """For known listings on this portal whose search-card price differs
    from the stored price, rewrite ``price`` to the new value and stash
    the previous one in ``price_previous`` plus a timestamp in
    ``price_changed_at``. Listings whose price is unchanged are touched
    only by the surrounding ``bump_last_seen`` call.

    Why this lives here rather than re-using ``_update_listing``: that
    function rewrites every field. We deliberately want a *minimal* diff
    — only the price and the change-marker, leaving the rest of the
    snapshot frozen. Returns ``{"changed": N, "checked": M}`` for
    runner stats.
    """
    if not observed:
        return {"changed": 0, "checked": 0}
    now = datetime.now(timezone.utc).isoformat()
    changed = 0
    async with async_session() as db:
        for chunk in _chunks(list(observed.keys())):
            rows = (
                await db.execute(
                    select(Listing.id, Listing.source_id, Listing.price, Listing.area_sqm).where(
                        Listing.source_portal == portal,
                        Listing.source_id.in_(chunk),
                    )
                )
            ).all()
            for row_id, sid, current, area in rows:
                new_price = observed[sid]
                if not _price_changed(current, new_price):
                    continue
                await db.execute(
                    update(Listing)
                    .where(Listing.id == row_id)
                    .values(
                        price=new_price,
                        price_previous=current,
                        price_changed_at=now,
                        price_per_sqm=round(new_price / area, 2) if area else None,
                    )
                )
                db.add(ListingPriceHistory(
                    listing_id=row_id, price=new_price, source_portal=portal, observed_at=now,
                ))
                changed += 1
        await db.commit()
    return {"changed": changed, "checked": len(observed)}


def _price_changed(before: float | None, after: float | None) -> bool:
    # Anything within €1 is unchanged — rounding noise on the portal side
    # ("165.000€" one day, "165.001€" the next).
    if after is None:
        return False
    return before is None or abs(after - before) >= 1.0


def _track_price(db: AsyncSession, listing: Listing, before: float | None, portal: str, now: str) -> None:
    """After ``listing.price`` may have been rewritten: stamp the change on
    the listing and append it to the price history."""
    if not _price_changed(before, listing.price):
        return
    if before is not None:
        listing.price_previous = before
        listing.price_changed_at = now
    db.add(ListingPriceHistory(
        listing_id=listing.id, price=listing.price, source_portal=portal, observed_at=now,
    ))


def _is_auction(item: ListingItem) -> bool:
    return item.is_auction or detect_auction(item.title, item.description)


def _mark_auction(listing: Listing, item: ListingItem) -> None:
    # One-way: any observation saying "auction" is enough (a portal
    # without a structured flag can't prove the opposite).
    if _is_auction(item):
        listing.is_auction = True


# Keep IN (...) lists under SQLite's bound-parameter limit.
_IN_CHUNK = 500


def _chunks(values: list[str]):
    for i in range(0, len(values), _IN_CHUNK):
        yield values[i : i + _IN_CHUNK]


async def bump_last_seen(portal: str, source_ids: list[str]) -> None:
    """Mark listings seen on ``portal``'s search pages as still live.

    Updates the portal's own canonical rows and source rows, *and* the
    canonical parent of any source row — a listing whose canonical portal
    dropped it but which casa.it still shows is still on the market. All
    touched rows are reactivated: being seen again is proof of life.
    """
    if not source_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    async with async_session() as db:
        for chunk in _chunks(source_ids):
            await db.execute(
                update(Listing)
                .where(Listing.source_portal == portal, Listing.source_id.in_(chunk))
                .values(last_seen_at=now, is_active=True)
            )
            await db.execute(
                update(ListingSource)
                .where(ListingSource.source_portal == portal, ListingSource.source_id.in_(chunk))
                .values(last_seen_at=now, is_active=True)
            )
            parents = select(ListingSource.listing_id).where(
                ListingSource.source_portal == portal, ListingSource.source_id.in_(chunk)
            )
            await db.execute(
                update(Listing)
                .where(Listing.id.in_(parents))
                .values(last_seen_at=now, is_active=True)
            )
        await db.commit()


async def refresh_source_urls(portal: str, urls: dict[str, str]) -> int:
    """Point known listings at the URL the portal uses *now*.

    The URL is a link, not part of the immutable content snapshot: when a
    portal migrates its URL scheme every stored link would 404 otherwise.
    Only rows whose URL actually differs are written. Returns the number of
    rows (canonical + source) updated.
    """
    if not urls:
        return 0
    changed = 0
    async with async_session() as db:
        for chunk in _chunks(list(urls)):
            listing_rows = (
                await db.execute(
                    select(Listing.id, Listing.source_id, Listing.listing_url).where(
                        Listing.source_portal == portal, Listing.source_id.in_(chunk)
                    )
                )
            ).all()
            for row_id, sid, current in listing_rows:
                if current != urls[sid]:
                    await db.execute(
                        update(Listing).where(Listing.id == row_id).values(listing_url=urls[sid])
                    )
                    changed += 1
            source_rows = (
                await db.execute(
                    select(ListingSource.id, ListingSource.source_id, ListingSource.source_url).where(
                        ListingSource.source_portal == portal, ListingSource.source_id.in_(chunk)
                    )
                )
            ).all()
            for row_id, sid, current in source_rows:
                if current != urls[sid]:
                    await db.execute(
                        update(ListingSource).where(ListingSource.id == row_id).values(source_url=urls[sid])
                    )
                    changed += 1
        await db.commit()
    return changed


async def cities_of_source_ids(portal: str, source_ids: list[str]) -> set[str]:
    """Lower-cased cities of the listings behind ``portal``'s source_ids:
    its own canonical rows and the canonical parents of its source rows."""
    cities: set[str] = set()
    async with async_session() as db:
        for chunk in _chunks(source_ids):
            own = select(Listing.city).where(
                Listing.source_portal == portal, Listing.source_id.in_(chunk)
            )
            parents = select(Listing.city).where(
                Listing.id.in_(
                    select(ListingSource.listing_id).where(
                        ListingSource.source_portal == portal, ListingSource.source_id.in_(chunk)
                    )
                )
            )
            for query in (own, parents):
                rows = await db.execute(query.distinct())
                cities.update(city.lower() for (city,) in rows if city)
    return cities


async def deactivate_stale_listings(portal: str, inactive_days: int, cities: set[str]) -> int:
    """Deactivate ``portal``'s canonical listings not seen on any portal for
    ``inactive_days`` (``last_seen_at`` already reflects every source, see
    bump_last_seen). Callers must only invoke this after a run with full
    catalog coverage — otherwise "not seen" just means "past the page cap".

    Scope is limited to ``cities``: the cities the run actually observed. A
    full scan of a Bari search proves nothing about the portal's Milano
    listings, while a province-wide search that saw Altamura listings does
    cover Altamura. Returns the number of listings deactivated.
    """
    if inactive_days <= 0 or not cities:
        return 0
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=inactive_days)).isoformat()
    in_scope = func.lower(Listing.city).in_(sorted(cities))
    async with async_session() as db:
        result = await db.execute(
            update(Listing)
            .where(
                Listing.source_portal == portal,
                Listing.is_active.is_(True),
                Listing.last_seen_at < cutoff,
                in_scope,
            )
            .values(is_active=False, updated_at=now.isoformat())
        )
        await db.execute(
            update(ListingSource)
            .where(
                ListingSource.source_portal == portal,
                ListingSource.is_active.is_(True),
                ListingSource.last_seen_at < cutoff,
                ListingSource.listing_id.in_(select(Listing.id).where(in_scope)),
            )
            .values(is_active=False)
        )
        await db.commit()
        return result.rowcount or 0


async def process_items_batch(
    items: list[ListingItem],
    scrape_run_id: str,
) -> dict[str, int]:
    """Process a batch of items with one shared DB session and a SAVEPOINT
    around each item. One commit per batch (amortized overhead), but a bad
    item only rolls back its own savepoint — the rest of the batch still
    commits successfully.
    """
    counts = {"new": 0, "updated": 0, "duplicate": 0, "skipped": 0, "errors": 0}
    if not items:
        return counts

    async with async_session() as db:
        for item in items:
            try:
                async with db.begin_nested():
                    result = await _process_single(db, item)
                counts[result] = counts.get(result, 0) + 1
            except Exception as e:
                counts["errors"] += 1
                logger.error(
                    "item_error_batch",
                    portal=item.source_portal,
                    source_id=item.source_id,
                    error=str(e),
                )
        await db.commit()
    return counts


def _portal_rank(portal: str) -> int:
    try:
        return PORTAL_PRIORITY.index(portal)
    except ValueError:
        return len(PORTAL_PRIORITY)


def _is_too_old(publication_date: str | None) -> bool:
    """True when the listing was published more than
    ``SCRAPE_MAX_LISTING_AGE_DAYS`` ago. 0 (the default) disables the cut.

    Spiders emit date-only strings ("2026-04-08"), which ``fromisoformat``
    parses as *naive* datetimes; comparing those with an aware cutoff
    raised TypeError, silently swallowed — so this filter never fired.
    We compare dates instead.
    """
    max_age = settings.SCRAPE_MAX_LISTING_AGE_DAYS
    if not publication_date or max_age <= 0:
        return False
    try:
        pub = datetime.fromisoformat(publication_date.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age)).date()
    return pub < cutoff


async def _process_single(db: AsyncSession, item: ListingItem) -> str:
    """Core upsert/dedup logic, reusing an existing session.
    Caller is responsible for commit/rollback.
    """
    # Normalise-and-validate incoming values before any branching. This
    # centralises bug-prone coercion (future dates, swapped coords, missing
    # city) so every spider benefits without hand-rolling its own checks.
    item.publication_date = clamp_publication_date(item.publication_date)
    item.lat, item.lng = clamp_italy_coords(item.lat, item.lng)
    if not item.city or item.city.strip().lower() in ("", "unknown"):
        # Listings without a city can't be deduped or searched — silently drop
        # rather than poison the DB with a shared "unknown" bucket.
        logger.debug("skipped_no_city", portal=item.source_portal, source_id=item.source_id)
        return "skipped"

    if _is_too_old(item.publication_date):
        logger.debug("skipped_old_listing", portal=item.source_portal, source_id=item.source_id, date=item.publication_date)
        return "skipped"

    now = datetime.now(timezone.utc).isoformat()

    # Step 1: Check exact match (same portal + same id).
    # First query the listings table (fast path for canonical listings),
    # then fall back to listing_sources — a previously-promoted listing
    # keeps its old portal identity only in the sources table.
    result = await db.execute(
        select(Listing).where(
            Listing.source_portal == item.source_portal,
            Listing.source_id == item.source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        src_result = await db.execute(
            select(ListingSource).where(
                ListingSource.source_portal == item.source_portal,
                ListingSource.source_id == item.source_id,
            )
        )
        existing_source = src_result.scalar_one_or_none()
        if existing_source:
            existing = await db.get(Listing, existing_source.listing_id)
            if existing:
                existing_source.price_on_source = item.price
                existing_source.last_seen_at = now
                existing_source.raw_data = json.dumps(item.raw_data, default=str)

    if existing:
        # Update canonical listing only if the incoming item is from the
        # same portal as the current canonical — otherwise we'd overwrite
        # higher-priority data. For lower-priority refreshes, just bump
        # last_seen_at and enrich empty fields.
        before = existing.price
        if existing.source_portal == item.source_portal:
            _update_listing(existing, item, now)
        else:
            _enrich_listing(existing, item, now)
        _track_price(db, existing, before, item.source_portal, now)
        _mark_auction(existing, item)
        return "updated"

    # Step 2: Check cross-portal duplicate
    normalized_addr = normalize_address(item.address, item.city)
    duplicate = await find_duplicate(
        db,
        city=item.city.lower(),
        listing_type=item.listing_type,
        property_type=item.property_type,
        address=item.address,
        price=item.price,
        area_sqm=item.area_sqm,
        rooms=item.rooms,
        lat=item.lat,
        lng=item.lng,
        exclude_portal=item.source_portal,
    )

    if duplicate:
        source = ListingSource(
            listing_id=duplicate.id,
            source_portal=item.source_portal,
            source_id=item.source_id,
            source_url=item.source_url,
            price_on_source=item.price,
            raw_data=json.dumps(item.raw_data, default=str),
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(source)

        # If the new item comes from a higher-priority portal (e.g. immobiliare)
        # than the current canonical, promote it — overwrite canonical fields
        # with the new item's data while keeping listing_id and all sources.
        before = duplicate.price
        if _portal_rank(item.source_portal) < _portal_rank(duplicate.source_portal):
            logger.info(
                "dedup_promote",
                new_portal=item.source_portal,
                old_portal=duplicate.source_portal,
                canonical_id=duplicate.id,
            )
            _promote_listing(duplicate, item, now)
        else:
            _enrich_listing(duplicate, item, now)
        _track_price(db, duplicate, before, item.source_portal, now)
        _mark_auction(duplicate, item)
        logger.info("dedup_merged", portal=item.source_portal, source_id=item.source_id, canonical_id=duplicate.id)
        return "duplicate"

    # Step 3: Create new listing
    price_per_sqm = None
    if item.price and item.area_sqm and item.area_sqm > 0:
        price_per_sqm = round(item.price / item.area_sqm, 2)

    listing = Listing(
        title=item.title,
        description=item.description,
        price=item.price,
        price_per_sqm=price_per_sqm,
        area_sqm=item.area_sqm,
        rooms=item.rooms,
        bedrooms=item.bedrooms,
        bathrooms=item.bathrooms,
        floor=item.floor,
        address=item.address,
        city=item.city.lower(),
        zone=item.zone,
        province=item.province,
        lat=item.lat,
        lng=item.lng,
        normalized_address=normalized_addr,
        images=json.dumps(item.images),
        floor_plans=json.dumps(item.floor_plans) if item.floor_plans else None,
        listing_url=item.source_url,
        source_portal=item.source_portal,
        source_id=item.source_id,
        energy_class=item.energy_class,
        property_type=item.property_type,
        listing_type=item.listing_type,
        condition=item.condition,
        heating=item.heating,
        has_elevator=item.has_elevator,
        has_balcony=item.has_balcony,
        has_terrace=item.has_terrace,
        has_garage=item.has_garage,
        has_garden=item.has_garden,
        condominium_fees=item.condominium_fees,
        year_built=item.year_built,
        publication_date=item.publication_date,
        is_auction=_is_auction(item),
        created_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
    )
    db.add(listing)
    await db.flush()
    _track_price(db, listing, None, item.source_portal, now)

    source = ListingSource(
        listing_id=listing.id,
        source_portal=item.source_portal,
        source_id=item.source_id,
        source_url=item.source_url,
        price_on_source=item.price,
        raw_data=json.dumps(item.raw_data, default=str),
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(source)
    return "new"


def _update_listing(listing: Listing, item: ListingItem, now: str) -> None:
    """Refresh canonical listing with new data from the same portal."""
    listing.title = item.title
    listing.description = item.description or listing.description
    listing.price = item.price
    listing.area_sqm = item.area_sqm or listing.area_sqm
    listing.rooms = item.rooms or listing.rooms
    listing.bedrooms = item.bedrooms or listing.bedrooms
    listing.bathrooms = item.bathrooms or listing.bathrooms
    listing.floor = item.floor or listing.floor
    listing.total_floors = item.total_floors or listing.total_floors
    listing.condition = item.condition or listing.condition
    listing.heating = item.heating or listing.heating
    listing.energy_class = item.energy_class or listing.energy_class
    listing.property_type = item.property_type or listing.property_type
    listing.zone = item.zone or listing.zone
    listing.province = item.province or listing.province
    listing.condominium_fees = item.condominium_fees if item.condominium_fees is not None else listing.condominium_fees
    listing.year_built = item.year_built or listing.year_built
    listing.last_seen_at = now
    listing.updated_at = now
    listing.is_active = True

    # Keep the earliest known publication date if we've already recorded one
    if item.publication_date and not listing.publication_date:
        listing.publication_date = item.publication_date

    if item.price and item.area_sqm and item.area_sqm > 0:
        listing.price_per_sqm = round(item.price / item.area_sqm, 2)

    if item.images:
        listing.images = json.dumps(item.images)
    if item.floor_plans:
        listing.floor_plans = json.dumps(item.floor_plans)
    if item.lat and not listing.lat:
        listing.lat = item.lat
        listing.lng = item.lng
    if item.address:
        listing.address = item.address
        listing.normalized_address = normalize_address(item.address, item.city)

    # Feature flags: overwrite when the new scrape has a concrete value
    for attr in ("has_elevator", "has_balcony", "has_terrace", "has_garage", "has_garden"):
        val = getattr(item, attr, None)
        if val is not None:
            setattr(listing, attr, val)


def _enrich_listing(listing: Listing, item: ListingItem, now: str) -> None:
    """Enrich canonical listing with data from a lower-priority source if missing."""
    listing.last_seen_at = now
    listing.updated_at = now
    # Re-seeing a listing from *any* portal means it's still live, so
    # reactivate it even if the incoming data is lower-priority and we're
    # not overwriting canonical fields.
    listing.is_active = True

    if not listing.lat and item.lat:
        listing.lat = item.lat
        listing.lng = item.lng
    if not listing.description and item.description:
        listing.description = item.description
    if not listing.energy_class and item.energy_class:
        listing.energy_class = item.energy_class
    if not listing.bathrooms and item.bathrooms:
        listing.bathrooms = item.bathrooms
    if not listing.bedrooms and item.bedrooms:
        listing.bedrooms = item.bedrooms
    if not listing.rooms and item.rooms:
        listing.rooms = item.rooms
    if not listing.area_sqm and item.area_sqm:
        listing.area_sqm = item.area_sqm
    if not listing.floor and item.floor:
        listing.floor = item.floor
    if not listing.total_floors and item.total_floors:
        listing.total_floors = item.total_floors
    if not listing.year_built and item.year_built:
        listing.year_built = item.year_built
    if listing.condominium_fees is None and item.condominium_fees is not None:
        listing.condominium_fees = item.condominium_fees
    if not listing.heating and item.heating:
        listing.heating = item.heating
    if not listing.condition and item.condition:
        listing.condition = item.condition
    if not listing.zone and item.zone:
        listing.zone = item.zone
    if not listing.province and item.province:
        listing.province = item.province
    if not listing.publication_date and item.publication_date:
        listing.publication_date = item.publication_date
    if not listing.floor_plans and item.floor_plans:
        listing.floor_plans = json.dumps(item.floor_plans)
    if not listing.address and item.address:
        listing.address = item.address
        listing.normalized_address = normalize_address(item.address, item.city)
    for attr in ("has_elevator", "has_balcony", "has_terrace", "has_garage", "has_garden"):
        if getattr(listing, attr, None) is None:
            val = getattr(item, attr, None)
            if val is not None:
                setattr(listing, attr, val)


def _promote_listing(listing: Listing, item: ListingItem, now: str) -> None:
    """Promote the new item as the canonical listing.

    Overwrites identity fields (source_portal, source_id, listing_url) and
    primary content with the new item's values. Keeps listing.id stable so
    existing ListingSource rows (including the old canonical's own source row)
    stay attached.
    """
    listing.source_portal = item.source_portal
    listing.source_id = item.source_id
    listing.listing_url = item.source_url
    listing.title = item.title
    if item.description:
        listing.description = item.description
    listing.price = item.price
    if item.area_sqm:
        listing.area_sqm = item.area_sqm
    if item.price and item.area_sqm and item.area_sqm > 0:
        listing.price_per_sqm = round(item.price / item.area_sqm, 2)
    if item.rooms is not None:
        listing.rooms = item.rooms
    if item.bedrooms is not None:
        listing.bedrooms = item.bedrooms
    if item.bathrooms is not None:
        listing.bathrooms = item.bathrooms
    if item.floor:
        listing.floor = item.floor
    if item.address:
        listing.address = item.address
        listing.normalized_address = normalize_address(item.address, item.city)
    if item.zone:
        listing.zone = item.zone
    if item.province:
        listing.province = item.province
    if item.lat is not None:
        listing.lat = item.lat
        listing.lng = item.lng
    if item.images:
        listing.images = json.dumps(item.images)
    if item.floor_plans:
        listing.floor_plans = json.dumps(item.floor_plans)
    if item.energy_class:
        listing.energy_class = item.energy_class
    if item.property_type:
        listing.property_type = item.property_type
    if item.condition:
        listing.condition = item.condition
    if item.heating:
        listing.heating = item.heating
    if item.has_elevator is not None:
        listing.has_elevator = item.has_elevator
    if item.has_balcony is not None:
        listing.has_balcony = item.has_balcony
    if item.has_terrace is not None:
        listing.has_terrace = item.has_terrace
    if item.has_garage is not None:
        listing.has_garage = item.has_garage
    if item.has_garden is not None:
        listing.has_garden = item.has_garden
    if item.condominium_fees is not None:
        listing.condominium_fees = item.condominium_fees
    if item.year_built is not None:
        listing.year_built = item.year_built
    if item.publication_date:
        listing.publication_date = item.publication_date
    listing.last_seen_at = now
    listing.updated_at = now
    listing.is_active = True
