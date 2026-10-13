import httpx
import pytest

from app.config import settings
from app.main import app
from app.models.alert import SearchAlert
from tests.conftest import make_listing

OLD = "2026-01-01T00:00:00+00:00"
SEEN = "2026-06-01T00:00:00+00:00"
NEW = "2026-09-01T00:00:00+00:00"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def catalog(db_session):
    db_session.add_all([
        make_listing(source_id="old", price=200000, first_seen_at=OLD),
        make_listing(source_id="new", price=180000, first_seen_at=NEW),
        make_listing(source_id="drop", price=150000, price_previous=170000, price_changed_at=NEW,
                     first_seen_at=OLD),
        make_listing(source_id="rise", price=190000, price_previous=170000, price_changed_at=NEW,
                     first_seen_at=OLD),
        make_listing(source_id="pricey", price=900000, first_seen_at=NEW),
        make_listing(source_id="milano", city="milano", price=100000, first_seen_at=NEW),
    ])
    await db_session.commit()


async def _create(client, name="Bari sotto 300k", **filters):
    return await client.post("/api/v1/alerts", json={"name": name, "filters": filters})


async def test_create_keeps_only_real_filters(client, catalog):
    r = await _create(client, city="bari", price_max="300000", page="2", sort="price_asc", zone="")
    assert r.status_code == 201
    body = r.json()
    assert body["filters"] == {"city": "bari", "price_max": "300000"}
    assert body["total"] == 4  # old, new, drop, rise
    # Just created: nothing is new yet.
    assert (body["new_count"], body["price_drop_count"]) == (0, 0)


async def test_counts_what_changed_since_the_last_look(client, catalog, db_session):
    alert_id = (await _create(client, city="bari", price_max="300000")).json()["id"]
    alert = await db_session.get(SearchAlert, alert_id)
    alert.seen_at = SEEN
    await db_session.commit()

    listed = (await client.get("/api/v1/alerts")).json()[0]
    # "new" was first seen after SEEN; "drop" got cheaper ("rise" doesn't count).
    assert (listed["new_count"], listed["price_drop_count"]) == (1, 1)

    seen = (await client.post(f"/api/v1/alerts/{alert_id}/seen")).json()
    assert (seen["new_count"], seen["price_drop_count"]) == (0, 0)


async def test_unknown_or_invalid_filters_are_rejected(client, catalog):
    assert (await _create(client, colour="blue")).status_code == 422
    bad = await _create(client, price_max="lots")
    assert bad.status_code == 422
    assert "price_max" in bad.json()["detail"]


async def test_rename_pause_and_delete(client, catalog):
    alert_id = (await _create(client, city="bari")).json()["id"]
    r = await client.patch(f"/api/v1/alerts/{alert_id}", json={"name": "Casa al mare", "is_active": False})
    assert (r.json()["name"], r.json()["is_active"]) == ("Casa al mare", False)

    assert (await client.delete(f"/api/v1/alerts/{alert_id}")).status_code == 204
    assert (await client.delete(f"/api/v1/alerts/{alert_id}")).status_code == 204
    assert (await client.get("/api/v1/alerts")).json() == []
    assert (await client.patch(f"/api/v1/alerts/{alert_id}", json={"name": "x"})).status_code == 404


async def test_mutations_need_the_admin_token_when_set(client, catalog, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "s3cret")
    assert (await _create(client, city="bari")).status_code == 401
    assert (await client.get("/api/v1/alerts")).status_code == 200


async def test_search_supports_the_since_filters(client, catalog):
    r = await client.get("/api/v1/listings", params={"city": "bari", "first_seen_after": SEEN})
    assert {i["source_id"] for i in r.json()["items"]} == {"new", "pricey"}
    r = await client.get("/api/v1/listings", params={"price_drop_since": SEEN})
    assert [i["source_id"] for i in r.json()["items"]] == ["drop"]
