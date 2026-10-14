import json

import httpx
import pytest
from sqlalchemy import select

from app.models.geocode import GeocodeCache
from app.models.listing import Listing
from app.services.geolocate import (
    Nominatim,
    locate_missing_listings,
    split_address,
    streets_in_text,
)
from scraper.items import ListingItem
from scraper.pipeline import process_items_batch
from tests.conftest import make_listing


class FakeGeocoder:
    """Stands in for Nominatim: canned answers by query, no network."""

    def __init__(self, answers: dict[str, dict] | None = None):
        self.answers = answers or {}
        self.asked: list[str] = []
        self.requests = 0

    async def search(self, query: str):
        self.asked.append(query)
        return self.answers.get(query)

    async def close(self):
        pass


def exact(id_, lat, lng, address=None, zone=None, city="bari"):
    return make_listing(source_id=id_, listing_url=f"https://example.com/{id_}", lat=lat, lng=lng,
                        address=address, zone=zone, city=city)


def unplaced(id_, address=None, zone=None, title="Appartamento", description=None, city="bari"):
    return make_listing(source_id=id_, listing_url=f"https://example.com/{id_}", lat=None, lng=None,
                        address=address, zone=zone, title=title, description=description, city=city,
                        source_portal="subito")


def town():
    """Five spread-out exact listings: Bari's centre is then (41.12, 16.87).
    Fresh objects per test: an instance added to an earlier test's session
    would not be inserted again."""
    return [exact(f"town{i}", 41.10 + i * 0.01, 16.85 + i * 0.01) for i in range(5)]


async def located(db_session, id_):
    db_session.expire_all()
    row = (await db_session.execute(select(Listing).where(Listing.source_id == id_))).scalar_one()
    return row.lat, row.lng, row.geo_precision


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize("raw, expected", [
    ("Via Amendola, 126", ("Via Amendola", "126")),
    ("via Giulio Petroni 12", ("via Giulio Petroni", "12")),
    ("Via don carlo gnocchi, , 9", ("Via don carlo gnocchi", "9")),
    ("Strada Messeni-Nemagna", ("Strada Messeni-Nemagna", None)),
    ("Via Battaglia di Montelungo al secondo piano", ("Via Battaglia di Montelungo", None)),
    ("via '' dell'Annunziata''", ("via dell'Annunziata", None)),
    ("Zona Poggiofranco", (None, None)),
    ("", (None, None)),
])
def test_split_address(raw, expected):
    assert split_address(raw) == expected


def test_streets_in_free_text():
    text = "Nuova costruzione – MyCity Bari\n\nBari – San Pasquale Alta, Via Fanelli\nvicino a corso Cavour 12, piano terra"
    assert streets_in_text(text) == ["Via Fanelli", "Corso Cavour"]
    assert streets_in_text("a breve distanza sia da Corso Umberto I che dalla stazione") == ["Corso Umberto I"]
    assert streets_in_text("via Michele Garruba ad altezza di via De Rossi") == ["Via Michele Garruba", "Via De Rossi"]


# ------------------------------------------------------------------ locating


async def test_street_without_number_goes_to_the_middle_of_the_street(db_session):
    db_session.add_all([*town(), exact("a", 41.050, 16.860, "Via Trabaccolanti"),
                        exact("b", 41.060, 16.870, "Via Trabaccolanti, 3"),
                        unplaced("x", address="Via Trabaccolanti")])
    await db_session.commit()

    assert await locate_missing_listings(use_network=False) == {"street": 1}
    assert await located(db_session, "x") == (pytest.approx(41.055), pytest.approx(16.865), "street")


async def test_house_number_already_known_is_an_address(db_session):
    db_session.add_all([*town(), exact("a", 41.11, 16.88, "Via Amendola, 126"),
                        unplaced("x", address="Via Amendola 126")])
    await db_session.commit()
    await locate_missing_listings(use_network=False)
    assert await located(db_session, "x") == (41.11, 16.88, "address")


async def test_a_street_in_the_zone_field_is_used_as_a_street(db_session):
    db_session.add_all([*town(), exact("a", 41.06, 16.92, "Via Virgilio"), exact("b", 41.062, 16.922, "Via Virgilio, 4"),
                        unplaced("x", zone="Via Virgilio")])
    await db_session.commit()
    await locate_missing_listings(use_network=False)
    assert await located(db_session, "x") == (pytest.approx(41.061), pytest.approx(16.921), "street")


@pytest.mark.parametrize("answer, placed", [
    ({"lat": 41.121, "lng": 16.867, "category": "highway", "type": "tertiary"}, True),  # a street's name
    ({"lat": 41.121, "lng": 16.867, "category": "place", "type": "suburb"}, False),  # a quarter: too vague
    ({"lat": 41.121, "lng": 16.867, "category": "leisure", "type": "stadium"}, False),  # a landmark
])
async def test_a_bare_name_in_the_zone_field_counts_only_if_it_is_a_street(db_session, answer, placed):
    db_session.add_all([*town(), unplaced("x", zone="Cesare Battisti")])
    await db_session.commit()
    await locate_missing_listings(use_network=True, geocoder=FakeGeocoder({"Cesare Battisti, bari": answer}))
    assert (await located(db_session, "x"))[2] == ("street" if placed else None)


async def test_subito_ad_placed_from_its_text(db_session):
    db_session.add_all([*town(), exact("a", 41.090, 16.890, "Via Giuseppe Fanelli"),
                        exact("b", 41.092, 16.892, "Via Giuseppe Fanelli, 8"),
                        unplaced("x", title="Trivani + box", description="Bari – San Pasquale Alta, Via Fanelli")])
    await db_session.commit()
    await locate_missing_listings(use_network=False)
    assert await located(db_session, "x") == (pytest.approx(41.091), pytest.approx(16.891), "street")


async def test_nominatim_answers_what_our_data_cannot(db_session):
    db_session.add_all([*town(), unplaced("x", address="Via Sparano"), unplaced("far", address="Via Roma")])
    await db_session.commit()
    geocoder = FakeGeocoder({
        "Via Sparano, bari": {"lat": 41.121, "lng": 16.868, "category": "highway", "type": "residential"},
        # a Via Roma 300 km away is another town's
        "Via Roma, bari": {"lat": 43.0, "lng": 13.0, "category": "highway", "type": "primary"},
    })
    assert await locate_missing_listings(use_network=True, geocoder=geocoder) == {"street": 1, "none": 1}
    assert await located(db_session, "x") == (41.121, 16.868, "street")
    assert await located(db_session, "far") == (None, None, None)


@pytest.mark.parametrize("listing", [
    dict(zone="Poggiofranco"),  # a quarter
    dict(title="Casa ristrutturata", description="Ottima occasione in zona servita"),  # nothing at all
])
async def test_without_a_street_there_is_no_pin(db_session, listing):
    db_session.add_all([*town(), exact("a", 41.10, 16.88, zone="Poggiofranco"),
                        exact("b", 41.11, 16.89, zone="Poggiofranco"), unplaced("x", **listing)])
    await db_session.commit()
    assert await locate_missing_listings(use_network=False) == {"none": 1}
    assert await located(db_session, "x") == (None, None, None)


async def test_coarser_estimates_are_taken_off_the_map(db_session):
    db_session.add_all([*town(), make_listing(source_id="old", listing_url="https://example.com/old",
                                              lat=41.12, lng=16.87, geo_precision="city")])
    await db_session.commit()
    await locate_missing_listings(use_network=False)
    assert await located(db_session, "old") == (None, None, None)


async def test_unplaced_listings_are_retried(db_session):
    db_session.add_all([*town(), unplaced("x", address="Via Sparano")])
    await db_session.commit()
    assert await locate_missing_listings(use_network=False) == {"none": 1}  # offline: unknown street
    geocoder = FakeGeocoder({"Via Sparano, bari": {"lat": 41.121, "lng": 16.868, "category": "highway"}})
    assert await locate_missing_listings(use_network=True, geocoder=geocoder) == {"street": 1}
    assert await located(db_session, "x") == (41.121, 16.868, "street")


async def test_portal_positions_are_never_touched(db_session):
    db_session.add_all([*town(), exact("a", 41.2, 16.9, "Via Trabaccolanti")])
    await db_session.commit()
    assert await locate_missing_listings(use_network=False) == {}
    assert await located(db_session, "a") == (41.2, 16.9, None)


# ---------------------------------------------------------- with the pipeline


def _item(**kw) -> ListingItem:
    fields = dict(source_portal="immobiliare", source_id="1", source_url="https://example.com/1",
                  title="Trilocale", city="Bari", property_type="apartment", listing_type="sale",
                  price=200000.0, area_sqm=80.0, rooms=3, address="Via Trabaccolanti")
    fields.update(kw)
    return ListingItem(**fields)


async def test_a_real_position_replaces_the_estimate(db_session):
    db_session.add_all([*town(), exact("a", 41.050, 16.860, "Via Trabaccolanti"),
                        exact("b", 41.060, 16.870, "Via Trabaccolanti, 3")])
    await db_session.commit()
    await process_items_batch([_item()], "run-1")  # no position
    await locate_missing_listings(use_network=False)
    assert (await located(db_session, "1"))[2] == "street"
    await process_items_batch([_item(lat=41.13, lng=16.86)], "run-2")  # now the portal gives one
    assert await located(db_session, "1") == (41.13, 16.86, None)


async def test_estimated_positions_are_no_evidence_of_a_duplicate(db_session):
    # Same estimated spot and similar figures: without the location the
    # match isn't near-identical, so they stay two listings.
    db_session.add(make_listing(source_id="c-1", source_portal="casa", address=None, price=206000.0,
                                area_sqm=80.0, rooms=3, lat=41.12, lng=16.87, geo_precision="street"))
    await db_session.commit()
    await process_items_batch([_item(source_id="i-1", address=None, lat=41.12, lng=16.87)], "run")
    db_session.expire_all()
    assert len((await db_session.execute(select(Listing))).scalars().all()) == 2


# ------------------------------------------------------------------ Nominatim


async def test_nominatim_client_caches_and_identifies_itself(db_session):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params["q"] == "Via Nowhere, bari":
            return httpx.Response(200, json=[])
        if request.url.params["q"] == "Via Down, bari":
            return httpx.Response(503)
        return httpx.Response(200, json=[{"lat": "41.1", "lon": "16.8", "category": "highway", "type": "residential"}])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    geocoder = Nominatim(client)
    geocoder.MIN_INTERVAL = 0

    hit = {"lat": 41.1, "lng": 16.8, "category": "highway", "type": "residential"}
    assert await geocoder.search("Via Sparano, bari") == hit
    assert await geocoder.search("Via Sparano, bari") == hit  # cached
    assert await geocoder.search("Via Nowhere, bari") is None
    assert await geocoder.search("Via Nowhere, bari") is None  # misses are cached too
    assert await geocoder.search("Via Down, bari") is None
    assert await geocoder.search("Via Down, bari") is None  # errors are retried, not cached
    await geocoder.close()

    assert [c.url.params["q"] for c in calls] == [
        "Via Sparano, bari", "Via Nowhere, bari", "Via Down, bari", "Via Down, bari"
    ]
    assert all(c.headers["user-agent"].startswith("Immo/") for c in calls)
    assert all(c.url.params["countrycodes"] == "it" for c in calls)
    cached = {r.query: r.result for r in (await db_session.execute(select(GeocodeCache))).scalars()}
    assert json.loads(cached["via sparano, bari"])["lat"] == 41.1
    assert cached["via nowhere, bari"] is None
    assert "via down, bari" not in cached
