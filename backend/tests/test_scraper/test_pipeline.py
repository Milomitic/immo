from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import settings
from app.models.listing import Listing, ListingSource
from scraper.items import ListingItem
from scraper.pipeline import (
    bump_last_seen,
    cities_of_source_ids,
    deactivate_stale_listings,
    get_known_source_ids,
    process_items_batch,
    refresh_source_urls,
    update_prices_from_observations,
)
from tests.conftest import make_listing


def item(**overrides) -> ListingItem:
    fields = dict(
        source_portal="immobiliare",
        source_id="100",
        source_url="https://example.com/100",
        title="Trilocale via Roma",
        city="Bari",
        property_type="apartment",
        listing_type="sale",
        price=200000.0,
        area_sqm=80.0,
        rooms=3,
        address="Via Roma 10",
        lat=41.12,
        lng=16.87,
    )
    fields.update(overrides)
    return ListingItem(**fields)


async def count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar()


async def test_new_listing_is_inserted(db_session):
    counts = await process_items_batch([item()], "run-1")
    assert counts["new"] == 1

    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.city == "bari"  # normalised to lowercase
    assert row.price_per_sqm == 2500.0
    assert await count(db_session, ListingSource) == 1


async def test_same_portal_and_id_is_an_update(db_session):
    await process_items_batch([item()], "run-1")
    counts = await process_items_batch([item(title="Trilocale ristrutturato")], "run-2")
    assert counts["updated"] == 1
    assert await count(db_session, Listing) == 1


async def test_unknown_city_is_skipped(db_session):
    counts = await process_items_batch([item(city="unknown")], "run-1")
    assert counts["skipped"] == 1
    assert await count(db_session, Listing) == 0


async def test_old_listing_kept_by_default(db_session):
    old = (datetime.now(timezone.utc) - timedelta(days=100)).date().isoformat()
    counts = await process_items_batch([item(publication_date=old)], "run-1")
    assert counts["new"] == 1


async def test_old_listing_skipped_when_max_age_set(db_session, monkeypatch):
    # Regression: date-only strings used to raise TypeError (naive vs
    # aware compare) inside _is_too_old, which swallowed it → never skipped.
    monkeypatch.setattr(settings, "SCRAPE_MAX_LISTING_AGE_DAYS", 60)
    old = (datetime.now(timezone.utc) - timedelta(days=100)).date().isoformat()
    counts = await process_items_batch([item(publication_date=old)], "run-1")
    assert counts["skipped"] == 1


async def test_swapped_coordinates_are_corrected(db_session):
    await process_items_batch([item(lat=16.87, lng=41.12)], "run-1")
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert (row.lat, row.lng) == (41.12, 16.87)


async def test_cross_portal_duplicate_attaches_as_source(db_session):
    await process_items_batch([item()], "run-1")
    counts = await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1")],
        "run-2",
    )
    assert counts["duplicate"] == 1
    assert await count(db_session, Listing) == 1
    assert await count(db_session, ListingSource) == 2


async def test_higher_priority_portal_is_promoted_to_canonical(db_session):
    # casa first, then the same flat appears on immobiliare (higher priority).
    await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1")],
        "run-1",
    )
    await process_items_batch([item()], "run-2")
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.source_portal == "immobiliare"
    assert row.source_id == "100"


async def test_rediscovered_source_reactivates_listing(db_session, session_factory):
    await process_items_batch([item()], "run-1")
    await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1")],
        "run-2",
    )
    async with session_factory() as s:
        row = (await s.execute(select(Listing))).scalar_one()
        row.is_active = False
        await s.commit()

    # casa sees it again → exact source match → enrich path → reactivated.
    await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1")],
        "run-3",
    )
    async with session_factory() as s:
        assert (await s.execute(select(Listing))).scalar_one().is_active is True


async def test_price_change_is_recorded(db_session):
    db_session.add(make_listing(source_id="1", price=200000.0, area_sqm=80.0))
    await db_session.commit()

    result = await update_prices_from_observations("immobiliare", {"1": 180000.0})
    assert result == {"changed": 1, "checked": 1}

    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.price == 180000.0
    assert row.price_previous == 200000.0
    assert row.price_changed_at is not None
    assert row.price_per_sqm == 2250.0


async def test_price_jitter_below_one_euro_is_ignored(db_session):
    db_session.add(make_listing(source_id="1", price=200000.0))
    await db_session.commit()

    result = await update_prices_from_observations("immobiliare", {"1": 200000.4})
    assert result["changed"] == 0


async def test_known_source_ids_cover_both_tables(db_session):
    db_session.add(make_listing(source_portal="casa", source_id="c-1"))
    canonical = make_listing(source_portal="immobiliare", source_id="i-1")
    db_session.add(canonical)
    await db_session.flush()
    db_session.add(ListingSource(
        listing_id=canonical.id, source_portal="casa", source_id="c-2",
        source_url="https://casa.it/c-2",
    ))
    await db_session.commit()

    assert await get_known_source_ids("casa") == {"c-1", "c-2"}


async def test_bump_via_secondary_source_keeps_canonical_alive(db_session):
    # immobiliare dropped the listing, casa.it still shows it: the canonical
    # row must count as seen (and come back if it had been deactivated).
    canonical = make_listing(source_portal="immobiliare", source_id="i-1",
                             last_seen_at="2020-01-01T00:00:00+00:00", is_active=False)
    db_session.add(canonical)
    await db_session.flush()
    db_session.add(ListingSource(listing_id=canonical.id, source_portal="casa",
                                 source_id="c-1", source_url="https://casa.it/c-1"))
    await db_session.commit()

    await bump_last_seen("casa", ["c-1"])

    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.is_active is True
    assert row.last_seen_at > "2020-01-01T00:00:00+00:00"


async def test_deactivate_only_stale_rows_of_that_portal(db_session):
    db_session.add_all([
        make_listing(source_portal="casa", source_id="old", last_seen_at="2020-01-01T00:00:00+00:00"),
        make_listing(source_portal="casa", source_id="fresh",
                     last_seen_at=datetime.now(timezone.utc).isoformat()),
        make_listing(source_portal="remax", source_id="other",
                     last_seen_at="2020-01-01T00:00:00+00:00"),
    ])
    await db_session.commit()

    assert await deactivate_stale_listings("casa", 14, {"bari"}) == 1

    db_session.expire_all()
    active = {r.source_id: r.is_active for r in (await db_session.execute(select(Listing))).scalars()}
    assert active == {"old": False, "fresh": True, "other": True}


async def test_deactivation_disabled_with_zero_days(db_session):
    db_session.add(make_listing(source_portal="casa", source_id="old",
                                last_seen_at="2020-01-01T00:00:00+00:00"))
    await db_session.commit()
    assert await deactivate_stale_listings("casa", 0, {"bari"}) == 0


async def test_deactivation_is_scoped_to_observed_cities(db_session):
    # A full scan of a Bari search says nothing about the portal's Milano
    # listings — they must survive even though they look stale.
    old = "2020-01-01T00:00:00+00:00"
    bari = make_listing(source_portal="casa", source_id="b", city="Bari", last_seen_at=old)
    milano = make_listing(source_portal="immobiliare", source_id="m", city="milano", last_seen_at=old)
    db_session.add_all([bari, milano])
    await db_session.flush()
    bari_id, milano_id = bari.id, milano.id
    db_session.add(ListingSource(listing_id=milano_id, source_portal="casa", source_id="cm",
                                 source_url="https://casa.it/cm", last_seen_at=old))
    await db_session.commit()

    assert await deactivate_stale_listings("casa", 14, {"bari"}) == 1
    assert await deactivate_stale_listings("casa", 14, set()) == 0

    db_session.expire_all()
    assert (await db_session.get(Listing, bari_id)).is_active is False
    assert (await db_session.get(Listing, milano_id)).is_active is True
    src = (await db_session.execute(select(ListingSource))).scalar_one()
    assert src.is_active is True


async def test_cities_of_source_ids_include_canonical_parents(db_session):
    own = make_listing(source_portal="casa", source_id="c-1", city="Altamura")
    parent = make_listing(source_portal="immobiliare", source_id="i-1", city="bari")
    db_session.add_all([own, parent])
    await db_session.flush()
    db_session.add(ListingSource(listing_id=parent.id, source_portal="casa",
                                 source_id="c-2", source_url="https://casa.it/c-2"))
    await db_session.commit()

    assert await cities_of_source_ids("casa", ["c-1", "c-2", "missing"]) == {"altamura", "bari"}


async def test_bump_last_seen_only_touches_timestamp(db_session):
    db_session.add(make_listing(source_id="1", price=200000.0))
    await db_session.commit()

    await bump_last_seen("immobiliare", ["1"])

    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.last_seen_at > "2026-01-01T00:00:00+00:00"
    assert row.price == 200000.0


async def test_refresh_source_urls_follows_portal_url_migration(db_session):
    # remax moved every listing to a new URL scheme: stored links must follow
    # (canonical and secondary rows), the content snapshot must not change.
    old, new = "https://www.remax.it/trova/immobile/X_1-2", "https://a.remax.it/vendita/bari/z-1-2"
    canonical = make_listing(source_portal="remax", source_id="1-2", listing_url=old, price=150000.0)
    other = make_listing(source_portal="immobiliare", source_id="9", listing_url="https://imm/9")
    db_session.add_all([canonical, other])
    await db_session.flush()
    db_session.add(ListingSource(listing_id=other.id, source_portal="remax",
                                 source_id="1-2", source_url=old))
    await db_session.commit()

    assert await refresh_source_urls("remax", {"1-2": new}) == 2
    assert await refresh_source_urls("remax", {"1-2": new}) == 0  # idempotent

    db_session.expire_all()
    rows = {r.source_id: r for r in (await db_session.execute(select(Listing))).scalars()}
    assert rows["1-2"].listing_url == new
    assert rows["1-2"].price == 150000.0
    assert rows["9"].listing_url == "https://imm/9"
    src = (await db_session.execute(select(ListingSource))).scalar_one()
    assert src.source_url == new
