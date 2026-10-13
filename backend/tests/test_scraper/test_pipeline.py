import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text, update

import scraper.pipeline as pipeline
from app.config import settings
from app.models.listing import Listing, ListingPriceHistory, ListingSource
from app.models.scrape_run import ScrapeRun
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


async def _history(session) -> list[tuple]:
    rows = await session.execute(select(ListingPriceHistory).order_by(ListingPriceHistory.id))
    return [(r.price, r.source_portal) for r in rows.scalars()]


async def test_new_listing_starts_its_price_history(db_session):
    await process_items_batch([item()], "run")
    assert await _history(db_session) == [(200000.0, "immobiliare")]


async def test_observed_price_change_extends_history(db_session):
    await process_items_batch([item()], "run")
    await update_prices_from_observations("immobiliare", {"100": 189000.0})
    await update_prices_from_observations("immobiliare", {"100": 189000.4})  # jitter: no point
    assert await _history(db_session) == [(200000.0, "immobiliare"), (189000.0, "immobiliare")]


async def test_same_portal_refresh_records_the_change(db_session):
    await process_items_batch([item()], "run-1")
    await process_items_batch([item(price=210000.0)], "run-2")

    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert (row.price, row.price_previous) == (210000.0, 200000.0)
    assert await _history(db_session) == [(200000.0, "immobiliare"), (210000.0, "immobiliare")]


async def test_promotion_logs_the_new_canonical_price(db_session):
    await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1", price=198000.0)],
        "run-1",
    )
    await process_items_batch([item()], "run-2")  # immobiliare takes over at 200k
    assert await _history(db_session) == [(198000.0, "casa"), (200000.0, "immobiliare")]


async def test_history_is_deleted_with_its_listing(db_session):
    await process_items_batch([item()], "run")
    await db_session.execute(delete(ListingSource))
    await db_session.execute(delete(Listing))
    await db_session.commit()
    assert await count(db_session, ListingPriceHistory) == 0  # FK ON DELETE CASCADE


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


async def test_auctions_are_flagged_from_text_or_structure(db_session):
    await process_items_batch([
        item(source_id="t", title="IMMOBILE IN ASTA - RESIDENZIALE", address="Via A 1", lat=41.10),
        item(source_id="s", title="Appartamento", is_auction=True, address="Via B 2", lat=41.11),
        item(source_id="n", title="Trilocale luminoso", address="Via C 3", lat=41.13),
    ], "run")
    flags = {r.source_id: r.is_auction for r in (await db_session.execute(select(Listing))).scalars()}
    assert flags == {"t": True, "s": True, "n": False}


async def test_a_duplicate_can_reveal_an_auction(db_session):
    await process_items_batch([item()], "run-1")
    await process_items_batch(
        [item(source_portal="casa", source_id="c-1", source_url="https://casa.it/c-1",
              description="Vendita giudiziaria, offerte entro il 30")],
        "run-2",
    )
    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.is_auction is True


AUCTION = {"date": "2027-01-22T16:30", "base_price": 79000.0, "court": "Tribunale di Bari"}


async def test_auction_data_is_stored_with_the_listing(db_session):
    await process_items_batch([item(is_auction=True, auction=AUCTION)], "run")
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert json.loads(row.auction_info) == AUCTION


async def test_auction_data_from_a_secondary_portal_reaches_the_canonical(db_session):
    await process_items_batch([item()], "run-1")
    await process_items_batch(
        [item(source_portal="wikicasa", source_id="w-1", source_url="https://www.wikicasa.it/annuncio/1",
              is_auction=True, auction=AUCTION)],
        "run-2",
    )
    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.source_portal == "immobiliare"  # still canonical
    assert row.is_auction is True
    assert json.loads(row.auction_info)["court"] == "Tribunale di Bari"


async def test_wikicasa_ranks_below_the_agencies_own_portals(db_session):
    await process_items_batch(
        [item(source_portal="wikicasa", source_id="w-1", source_url="https://www.wikicasa.it/annuncio/1")], "run-1"
    )
    await process_items_batch([item(source_portal="tecnocasa", source_id="t-1", source_url="https://t/1")], "run-2")
    db_session.expire_all()
    row = (await db_session.execute(select(Listing))).scalar_one()
    assert row.source_portal == "tecnocasa"  # promoted over the republisher


async def test_locationless_listings_merge_only_when_near_identical(db_session):
    await process_items_batch([item()], "run-1")  # has address and coordinates
    nowhere = dict(source_portal="subito", address=None, lat=None, lng=None)
    # 3% cheaper, same size and rooms: plausibly a different flat
    await process_items_batch(
        [item(source_id="s-1", source_url="https://www.subito.it/a-1.htm", price=194000.0, **nowhere)], "run-2"
    )
    # same figures: the agency's ad republished on Subito
    await process_items_batch(
        [item(source_id="s-2", source_url="https://www.subito.it/a-2.htm", **nowhere)], "run-3"
    )
    db_session.expire_all()
    portals = sorted(r.source_portal for r in (await db_session.execute(select(Listing))).scalars())
    assert portals == ["immobiliare", "subito"]  # s-1 stands on its own
    assert await count(db_session, ListingSource) == 3  # s-2 joined the original


async def test_a_concurrent_commit_mid_batch_does_not_lose_the_batch(session_factory, monkeypatch):
    """The runner's progress heartbeat commits every 2s on its own
    connection. A batch that has read before such a commit and writes after
    it must still go through: it used to fail as a whole with "database is
    locked" (a stale WAL snapshot, which busy_timeout can't wait out)."""
    async with session_factory() as s:
        await s.execute(text("PRAGMA journal_mode=WAL"))  # as in production
        s.add(ScrapeRun(id="hb", portal="x", status="running"))
        await s.commit()

    async def heartbeat():
        async with session_factory() as s:
            await s.execute(update(ScrapeRun).where(ScrapeRun.id == "hb").values(progress_done=1))
            await s.commit()

    original = pipeline.find_duplicate
    tasks = []

    async def find_duplicate_then_yield(*args, **kwargs):
        found = await original(*args, **kwargs)  # the batch has read...
        tasks.append(asyncio.create_task(heartbeat()))
        await asyncio.sleep(0.3)  # ...and the other connection gets its turn
        return found

    monkeypatch.setattr(pipeline, "find_duplicate", find_duplicate_then_yield)
    counts = await process_items_batch([item()], "run")
    await asyncio.gather(*tasks)  # the heartbeat got through too, after the batch

    assert counts["errors"] == 0 and counts["new"] == 1
    async with session_factory() as s:
        assert (await s.get(ScrapeRun, "hb")).progress_done == 1
