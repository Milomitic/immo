from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def apply_sqlite_pragmas(async_engine) -> None:
    """SQLite PRAGMAs are per-connection, so they must be set on every new
    connection, not once at startup. busy_timeout makes a writer wait for
    the lock instead of failing with "database is locked" when the scraper
    subprocess and the API write at the same time."""

    @event.listens_for(async_engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()


if _IS_SQLITE:
    apply_sqlite_pragmas(engine)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


# First Alembic revision. Databases created before Alembic was introduced
# already have this schema (built by create_all + hand-run ALTERs), so they
# are stamped at this revision rather than migrated from scratch.
_BASELINE_REVISION = "0001"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _backup_sqlite(db_path: Path, label: str) -> Path:
    """Copy a live SQLite DB (WAL-safe, via the backup API) before changing
    its schema. Keeps the 5 most recent backups."""
    import sqlite3
    from datetime import datetime

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{db_path.stem}-before-{label}-{stamp}.db"
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest)
        src.backup(dst)
        dst.close()
    finally:
        src.close()
    for old in sorted(backup_dir.glob(f"{db_path.stem}-before-*.db"))[:-5]:
        old.unlink()
    return dest


async def init_db(target_engine=None) -> None:
    """Bring the schema to the latest Alembic revision at startup.

    Before applying pending migrations to an existing SQLite file, the DB is
    backed up to ``data/backups/`` — with ``uvicorn --reload`` a migration
    file applies the moment it's saved, so this is the undo button.
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    target_engine = target_engine or engine
    cfg = _alembic_config()
    db_file = target_engine.url.database if target_engine.url.get_backend_name() == "sqlite" else None

    def _upgrade(sync_conn) -> None:
        tables = set(inspect(sync_conn).get_table_names())
        cfg.attributes["connection"] = sync_conn
        if "listings" in tables and "alembic_version" not in tables:
            command.stamp(cfg, _BASELINE_REVISION)
        current = MigrationContext.configure(sync_conn).get_current_revision()
        head = ScriptDirectory.from_config(cfg).get_current_head()
        if db_file and "listings" in tables and current != head:
            _backup_sqlite(Path(db_file), current or "unversioned")
        command.upgrade(cfg, "head")

    async with target_engine.begin() as conn:
        if target_engine.url.get_backend_name() == "sqlite":
            await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(_upgrade)
