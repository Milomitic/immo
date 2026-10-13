import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database as database
import app.models  # noqa: F401  (registers every table on Base.metadata)
import scraper.pipeline  # noqa: F401  (imports async_session by name — must be patched)
from app.database import Base
from app.models.listing import Listing

_ORIGINAL_FACTORY = database.async_session


@pytest.fixture(autouse=True)
async def session_factory(tmp_path, monkeypatch):
    """Per-test SQLite file DB, swapped in for the real one everywhere.

    Several modules do ``from app.database import async_session``, so
    patching ``app.database`` alone isn't enough — we replace the factory
    in every loaded module that holds a reference to the original. Being
    autouse, no test can reach ``data/immo.db`` even by accident.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.apply_sqlite_pragmas(engine)  # same FK enforcement as production
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    for mod in list(sys.modules.values()):
        if getattr(mod, "async_session", None) is _ORIGINAL_FACTORY:
            monkeypatch.setattr(mod, "async_session", factory)

    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch):
    """A spawned scraper wouldn't inherit our DB patching and would write to
    the real data/immo.db. Tests must stub launch_scrape; this makes any
    leak fail loudly instead of silently scraping."""
    import app.services.scrape_service as svc

    def _forbidden(*args, **kwargs):
        raise AssertionError(f"tests must not spawn processes: {args!r}")

    monkeypatch.setattr(svc.subprocess, "Popen", _forbidden)
    monkeypatch.setattr(svc, "_last_launch_monotonic", None)


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


_NOW = "2026-01-01T00:00:00+00:00"


def make_listing(**overrides) -> Listing:
    """Build a Listing with sane defaults; override any column by kwarg."""
    fields = dict(
        title="Trilocale centro",
        city="bari",
        listing_url="https://example.com/1",
        source_portal="immobiliare",
        source_id="1",
        property_type="apartment",
        listing_type="sale",
        price=200000.0,
        area_sqm=80.0,
        price_per_sqm=2500.0,
        rooms=3,
        lat=41.12,
        lng=16.87,
        images="[]",
        created_at=_NOW,
        updated_at=_NOW,
        first_seen_at=_NOW,
        last_seen_at=_NOW,
        is_active=True,
    )
    fields.update(overrides)
    return Listing(**fields)
