import httpx
import pytest
from sqlalchemy import delete, func, select

from app.config import settings
from app.main import app
from app.models.favorite import Favorite
from app.models.listing import Listing
from tests.conftest import make_listing


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def ids(db_session):
    rows = [
        make_listing(source_id="a", title="Bilocale"),
        make_listing(source_id="b", title="Villa", is_active=False),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return {r.source_id: r.id for r in rows}


async def test_save_is_idempotent(client, ids):
    first = await client.put(f"/api/v1/favorites/{ids['a']}")
    again = await client.put(f"/api/v1/favorites/{ids['a']}")
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["listing"]["title"] == "Bilocale"
    assert (await client.get("/api/v1/favorites/ids")).json() == [ids["a"]]


async def test_list_keeps_listings_that_left_the_market(client, ids):
    await client.put(f"/api/v1/favorites/{ids['a']}")
    await client.put(f"/api/v1/favorites/{ids['b']}")
    body = (await client.get("/api/v1/favorites")).json()
    assert {f["listing"]["title"]: f["listing"]["is_active"] for f in body} == {
        "Bilocale": True, "Villa": False,
    }


async def test_remove_is_idempotent(client, ids):
    await client.put(f"/api/v1/favorites/{ids['a']}")
    assert (await client.delete(f"/api/v1/favorites/{ids['a']}")).status_code == 204
    assert (await client.delete(f"/api/v1/favorites/{ids['a']}")).status_code == 204
    assert (await client.get("/api/v1/favorites/ids")).json() == []


async def test_unknown_listing_is_404(client, ids):
    assert (await client.put("/api/v1/favorites/nope")).status_code == 404


async def test_mutations_need_the_admin_token_when_set(client, ids, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "s3cret")
    assert (await client.put(f"/api/v1/favorites/{ids['a']}")).status_code == 401
    ok = await client.put(f"/api/v1/favorites/{ids['a']}", headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 201
    assert (await client.get("/api/v1/favorites")).status_code == 200  # reads stay open


async def test_favorite_goes_with_its_listing(client, ids, db_session):
    await client.put(f"/api/v1/favorites/{ids['a']}")
    await db_session.execute(delete(Listing).where(Listing.id == ids["a"]))
    await db_session.commit()
    assert (await db_session.execute(select(func.count()).select_from(Favorite))).scalar() == 0
