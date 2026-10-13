"""Text search: FTS5 when the index exists (a migrated database), LIKE
otherwise (the create_all schema the other tests use)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import apply_sqlite_pragmas, init_db
from app.schemas.listing import ListingSearchParams
from app.services.listing_service import fts_match_query, get_listing_markers, search_listings
from tests.conftest import make_listing


def _listings():
    return [
        make_listing(source_id="1", title="Trilocale in centro",
                     description="Vista sulla città, con ascensore"),
        make_listing(source_id="2", title="Villa con giardino", zone="Poggiofranco",
                     description="Quartiere residenziale"),
        make_listing(source_id="3", title="Bilocale", description="Città vecchia", is_active=False),
    ]


@pytest.fixture
async def migrated_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'fts.db').as_posix()}")
    apply_sqlite_pragmas(engine)
    await init_db(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(_listings())
        await session.commit()
        yield session
    await engine.dispose()


async def _titles(session, q: str) -> list[str]:
    page = await search_listings(session, ListingSearchParams(q=q))
    return sorted(item.title for item in page.items)


def test_match_query_stems_long_words_and_keeps_short_ones_exact():
    assert fts_match_query('Terrazzo "giardino"') == '"terrazz"* "giardin"*'
    assert fts_match_query("box auto") == '"box" "auto"'  # not "autonomo"
    assert fts_match_query("Murat") == '"murat"*'
    assert fts_match_query("  ?!  ") is None


async def test_fts_matches_gender_and_number_variants(migrated_session):
    # "giardini" (plural) still finds "giardino".
    assert await _titles(migrated_session, "giardini") == ["Villa con giardino"]


async def test_fts_is_accent_insensitive(migrated_session):
    # The inactive "Città vecchia" listing stays out, as with every filter.
    assert await _titles(migrated_session, "citta") == ["Trilocale in centro"]


async def test_fts_matches_word_prefixes_across_columns(migrated_session):
    assert await _titles(migrated_session, "trilo") == ["Trilocale in centro"]
    assert await _titles(migrated_session, "poggio") == ["Villa con giardino"]  # zone column


async def test_fts_requires_every_word(migrated_session):
    assert await _titles(migrated_session, "villa giardino") == ["Villa con giardino"]
    assert await _titles(migrated_session, "villa ascensore") == []


async def test_query_syntax_in_user_input_is_harmless(migrated_session):
    assert await _titles(migrated_session, 'centro" (*') == ["Trilocale in centro"]


async def test_map_markers_use_the_same_search(migrated_session):
    markers = await get_listing_markers(migrated_session, ListingSearchParams(q="giardin"))
    assert [m.title for m in markers.markers] == ["Villa con giardino"]


async def test_like_fallback_without_index(db_session):
    db_session.add_all(_listings())
    await db_session.commit()
    assert await _titles(db_session, "centro") == ["Trilocale in centro"]
    # Substring semantics, no accent folding: the reason FTS exists.
    assert await _titles(db_session, "citta") == []
