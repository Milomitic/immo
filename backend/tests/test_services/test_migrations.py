"""Alembic migrations must produce exactly the schema the models declare,
both from an empty database and from a pre-Alembic one (create_all +
hand-run ALTERs, which is what existing installs have)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base, apply_sqlite_pragmas, include_schema_name, init_db


async def _schema_diff(engine) -> list:
    def _diff(sync_conn):
        # Same name filter as alembic/env.py: the FTS index isn't a model.
        ctx = MigrationContext.configure(sync_conn, opts={"include_name": include_schema_name})
        return compare_metadata(ctx, Base.metadata)

    async with engine.connect() as conn:
        return await conn.run_sync(_diff)


async def _revision(engine) -> str:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()


def _engine(tmp_path, name):
    eng = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}")
    apply_sqlite_pragmas(eng)
    return eng


async def test_fresh_database_migrates_to_models(tmp_path):
    engine = _engine(tmp_path, "fresh.db")
    await init_db(engine)
    assert await _schema_diff(engine) == []
    await engine.dispose()


async def test_legacy_database_is_stamped_then_upgraded(tmp_path):
    engine = _engine(tmp_path, "legacy.db")
    # Simulate a pre-Alembic install: the baseline schema exists but there
    # is no alembic_version table (create_all + hand-run ALTERs).
    from alembic import command

    from app.database import _alembic_config

    cfg = _alembic_config()

    def _to_baseline(sync_conn):
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "0001")
        sync_conn.execute(text("DROP TABLE alembic_version"))

    async with engine.begin() as conn:
        await conn.run_sync(_to_baseline)
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "alembic_version" not in tables
    assert "scrape_errors" not in tables  # added after the baseline

    await init_db(engine)
    assert await _schema_diff(engine) == []
    assert await _revision(engine)  # stamped at baseline, then upgraded to head
    await engine.dispose()


async def test_pending_migration_backs_up_existing_db(tmp_path):
    engine = _engine(tmp_path, "data.db")
    from alembic import command

    from app.database import _alembic_config

    cfg = _alembic_config()

    def _to_baseline(sync_conn):
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "0001")

    async with engine.begin() as conn:
        await conn.run_sync(_to_baseline)

    await init_db(engine)
    backups = list((tmp_path / "backups").glob("data-before-0001-*.db"))
    assert len(backups) == 1
    await engine.dispose()


async def test_no_backup_when_already_at_head(tmp_path):
    engine = _engine(tmp_path, "fresh.db")
    await init_db(engine)  # creates from scratch: nothing to back up
    await init_db(engine)  # already at head
    assert not (tmp_path / "backups").exists()
    await engine.dispose()


async def test_init_db_is_idempotent(tmp_path):
    engine = _engine(tmp_path, "twice.db")
    await init_db(engine)
    head = await _revision(engine)
    await init_db(engine)
    assert await _revision(engine) == head
    await engine.dispose()


_INSERT_LISTING = text(
    "INSERT INTO listings (id, title, city, listing_url, source_portal, source_id, property_type,"
    " listing_type, price, price_previous, price_changed_at,"
    " created_at, updated_at, first_seen_at, last_seen_at, is_active)"
    " VALUES (:id, 'Trilocale', 'bari', 'u', 'casa', :id, 'apartment', 'sale',"
    " :price, :prev, :changed, '2026-01-01', '2026-01-01', '2026-01-01', '2026-01-01', 1)"
)


async def test_price_history_is_backfilled_from_listing_columns(tmp_path):
    engine = _engine(tmp_path, "history.db")
    from alembic import command

    from app.database import _alembic_config

    cfg = _alembic_config()

    def _to_0003(sync_conn):
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "0003")

    async with engine.begin() as conn:
        await conn.run_sync(_to_0003)
        await conn.execute(_INSERT_LISTING, {"id": "changed", "price": 180000, "prev": 200000,
                                             "changed": "2026-03-01"})
        await conn.execute(_INSERT_LISTING, {"id": "steady", "price": 150000, "prev": None,
                                             "changed": None})
        await conn.execute(_INSERT_LISTING, {"id": "no-price", "price": None, "prev": None,
                                             "changed": None})

    await init_db(engine)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT listing_id, price, observed_at FROM listing_price_history"
            " ORDER BY listing_id, observed_at"
        ))).all()
    assert [tuple(r) for r in rows] == [
        ("changed", 200000.0, "2026-01-01"),
        ("changed", 180000.0, "2026-03-01"),
        ("steady", 150000.0, "2026-01-01"),
    ]
    await engine.dispose()


async def test_fulltext_index_follows_inserts_updates_and_deletes(tmp_path):
    engine = _engine(tmp_path, "fts.db")
    await init_db(engine)

    async def hits(term: str) -> list[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(text(
                "SELECT l.id FROM listings l WHERE l.rowid IN"
                " (SELECT rowid FROM listings_fts WHERE listings_fts MATCH :q) ORDER BY l.id"
            ), {"q": term})
            return [r[0] for r in rows]

    async with engine.begin() as conn:
        await conn.execute(_INSERT_LISTING, {"id": "a", "price": 1, "prev": None, "changed": None})
        await conn.execute(text("UPDATE listings SET description = 'Vista sulla città' WHERE id = 'a'"))
    assert await hits('"citta"') == ["a"]  # accent-insensitive

    async with engine.begin() as conn:
        await conn.execute(text("UPDATE listings SET description = 'Vista mare' WHERE id = 'a'"))
    assert await hits('"citta"') == []
    assert await hits('"mar"*') == ["a"]

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM listings WHERE id = 'a'"))
    assert await hits('"mare"') == []
    await engine.dispose()


async def test_auction_flag_is_backfilled_without_breaking_search_index(tmp_path):
    engine = _engine(tmp_path, "auction.db")
    from alembic import command

    from app.database import _alembic_config

    cfg = _alembic_config()

    def _to_0007(sync_conn):
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "0007")

    async with engine.begin() as conn:
        await conn.run_sync(_to_0007)
        await conn.execute(_INSERT_LISTING, {"id": "a", "price": 1, "prev": None, "changed": None})
        await conn.execute(_INSERT_LISTING, {"id": "b", "price": 1, "prev": None, "changed": None})
        await conn.execute(text("UPDATE listings SET title = 'IMMOBILE IN ASTA' WHERE id = 'a'"))

    await init_db(engine)
    async with engine.connect() as conn:
        flags = dict((await conn.execute(text("SELECT id, is_auction FROM listings"))).all())
        triggers = {r[0] for r in await conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))}
        hits = (await conn.execute(text(
            "SELECT count(*) FROM listings_fts WHERE listings_fts MATCH '\"asta\"'"
        ))).scalar()
    assert flags == {"a": 1, "b": 0}
    assert {"listings_fts_ai", "listings_fts_ad", "listings_fts_au"} <= triggers
    assert hits == 1
    await engine.dispose()


_INSERT_TITLED = text(
    "INSERT INTO listings (id, title, city, address, zone, rooms, listing_url, source_portal, source_id,"
    " property_type, listing_type, created_at, updated_at, first_seen_at, last_seen_at, is_active)"
    " VALUES (:id, :title, 'bari', :address, :zone, :rooms, 'u', :portal, :id, :ptype, 'sale',"
    " '2026-01-01', '2026-01-01', '2026-01-01', '2026-01-01', 1)"
)


async def test_boilerplate_immobiliare_titles_are_rebuilt(tmp_path):
    engine = _engine(tmp_path, "titles.db")
    from alembic import command

    from app.database import _alembic_config

    cfg = _alembic_config()

    def _to_0009(sync_conn):
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "0009")

    slogan = "Acquisto Assistito in Asta e Pre-Asta"

    def row(id_, title, address, zone="Murat", rooms=3, portal="immobiliare", ptype="apartment"):
        return {"id": id_, "title": title, "address": address, "zone": zone, "rooms": rooms,
                "portal": portal, "ptype": ptype}

    rows = [
        # contact details: rebuilt even when unique
        row("api", "Lavora in A.P.I. Srl -Curriculum studio@apisrl.org", "Via don carlo gnocchi, , 9",
            zone="San Paolo, Stanic", rooms=5),
        # one slogan at three different addresses: describes none of them
        row("s1", slogan, "via Roma 1", rooms=2),
        row("s2", slogan, "via Sparano 2", rooms=1, ptype="studio"),
        row("s3", slogan, None, zone=None, rooms=None, ptype="villa"),
        # left alone: a descriptive caption, a duplicate pair at one address,
        # and another portal's titles
        row("keep", "Eleganza senza tempo nel cuore del Quartiere Umbertino", "via Montenegro 19"),
        row("dup1", "AMPIO TRILOCALE", "via Calefati 10"),
        row("dup2", "AMPIO TRILOCALE", "via Calefati 10"),
        *(row(f"c{i}", "Trilocale", f"via Casa {i}", portal="casa") for i in range(3)),
    ]
    async with engine.begin() as conn:
        await conn.run_sync(_to_0009)
        for r in rows:
            await conn.execute(_INSERT_TITLED, r)

    await init_db(engine)
    async with engine.connect() as conn:
        titles = dict((await conn.execute(text("SELECT id, title FROM listings"))).all())
        hits = (await conn.execute(text(
            "SELECT count(*) FROM listings_fts WHERE listings_fts MATCH '\"curriculum\"'"
        ))).scalar()

    assert titles["api"] == "Pentalocale Via don carlo gnocchi 9, San Paolo, Stanic, Bari"
    assert titles["s1"] == "Bilocale via Roma 1, Murat, Bari"
    assert titles["s2"] == "Monolocale via Sparano 2, Murat, Bari"
    assert titles["s3"] == "Villa, Bari"
    assert titles["keep"] == "Eleganza senza tempo nel cuore del Quartiere Umbertino"
    assert titles["dup1"] == titles["dup2"] == "AMPIO TRILOCALE"
    assert {titles[f"c{i}"] for i in range(3)} == {"Trilocale"}
    assert hits == 0  # the search index followed the new titles
    await engine.dispose()
