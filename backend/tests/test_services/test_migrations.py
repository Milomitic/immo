"""Alembic migrations must produce exactly the schema the models declare,
both from an empty database and from a pre-Alembic one (create_all +
hand-run ALTERs, which is what existing installs have)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base, apply_sqlite_pragmas, init_db


async def _schema_diff(engine) -> list:
    def _diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn)
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
