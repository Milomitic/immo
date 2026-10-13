import httpx
import pytest

from app.main import app
from app.models.listing import ListingSource
from tests.conftest import make_listing

# Inside the Bari test square: (41.12, 16.87). Outside: (41.30, 16.87).
SQUARE = "41.10,16.85;41.10,16.90;41.14,16.90;41.14,16.85"


@pytest.fixture
async def client():
    # ASGITransport doesn't run the lifespan, so the real DB is never
    # initialised; get_db is already redirected by the autouse fixture.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded(db_session):
    rows = [
        make_listing(source_id="a", title="Bilocale centro", price=150000, rooms=2, area_sqm=60,
                     price_per_sqm=2500, lat=41.12, lng=16.87),
        make_listing(source_id="b", title="Trilocale Poggiofranco", price=250000, rooms=3, area_sqm=100,
                     price_per_sqm=2500, lat=41.11, lng=16.86, description="con terrazzo panoramico"),
        make_listing(source_id="c", title="Villa Torre a Mare", price=600000, rooms=6, area_sqm=250,
                     price_per_sqm=2400, property_type="villa", lat=41.30, lng=16.87),
        make_listing(source_id="d", title="Monolocale Molfetta", city="molfetta", price=90000, rooms=1,
                     area_sqm=35, price_per_sqm=2571, lat=41.20, lng=16.59),
        make_listing(source_id="e", title="Venduto", price=100000, is_active=False),
    ]
    db_session.add_all(rows)
    await db_session.flush()
    db_session.add(ListingSource(listing_id=rows[0].id, source_portal="casa", source_id="ca",
                                 source_url="https://casa.it/ca"))
    await db_session.commit()
    return {r.source_id: r.id for r in rows}


async def get_ids(client, **params) -> list[str]:
    r = await client.get("/api/listings", params=params)
    assert r.status_code == 200
    return [it["source_id"] for it in r.json()["items"]]


async def test_inactive_listings_are_hidden(client, seeded):
    ids = await get_ids(client)
    assert "e" not in ids
    assert len(ids) == 4


async def test_city_filter(client, seeded):
    assert await get_ids(client, city="Molfetta") == ["d"]


async def test_price_and_rooms_filters(client, seeded):
    assert set(await get_ids(client, price_min=100000, price_max=300000)) == {"a", "b"}
    assert set(await get_ids(client, rooms_min=3)) == {"b", "c"}


async def test_property_type_filter(client, seeded):
    assert await get_ids(client, property_type="villa") == ["c"]


async def test_sort_price_asc(client, seeded):
    assert await get_ids(client, sort="price_asc") == ["d", "a", "b", "c"]


async def test_text_search_matches_description(client, seeded):
    assert await get_ids(client, q="terrazzo") == ["b"]


async def test_pagination(client, seeded):
    r = await client.get("/api/listings", params={"page_size": 3, "sort": "price_asc"})
    body = r.json()
    assert body["total"] == 4
    assert body["total_pages"] == 2
    page2 = await get_ids(client, page=2, page_size=3, sort="price_asc")
    assert page2 == ["c"]


async def test_polygon_filter_is_exact(client, seeded):
    ids = await get_ids(client, polygon=SQUARE)
    assert set(ids) == {"a", "b"}


async def test_malformed_polygon_is_ignored(client, seeded):
    assert len(await get_ids(client, polygon="garbage")) == 4


async def test_map_markers_with_polygon(client, seeded):
    r = await client.get("/api/listings/map", params={"polygon": SQUARE})
    body = r.json()
    assert body["total"] == 2
    assert {m["id"] for m in body["markers"]} == {seeded["a"], seeded["b"]}


async def test_detail_includes_sources(client, seeded):
    r = await client.get(f"/api/listings/{seeded['a']}")
    assert r.status_code == 200
    body = r.json()
    assert body["source_count"] == 1
    assert body["sources"][0]["source_portal"] == "casa"


async def test_detail_404(client, seeded):
    r = await client.get("/api/listings/does-not-exist")
    assert r.status_code == 404


async def test_similar_listings(client, seeded):
    r = await client.get(f"/api/listings/{seeded['a']}/similar")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
