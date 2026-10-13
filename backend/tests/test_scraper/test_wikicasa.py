"""WikicasaSpider on synthetic pages shaped like the site's Nuxt payloads."""

import json

import pytest

from scraper.spiders.base import SearchParams
from scraper.spiders.wikicasa import WikicasaSpider
from scraper.utils.rate_limiter import RateLimiter


def flatten(obj) -> list:
    """devalue-style flattening (every value in its own slot), with the
    Vue wrapper Nuxt puts around the root."""
    values: list = [["ShallowReactive", 1]]

    def add(v):
        idx = len(values)
        values.append(None)
        if isinstance(v, dict):
            values[idx] = {k: add(x) for k, x in v.items()}
        elif isinstance(v, list):
            values[idx] = [add(x) for x in v]
        else:
            values[idx] = v
        return idx

    add(obj)
    return values


def nuxt_page(stores: dict, body: str = "") -> str:
    payload = json.dumps(flatten({"pinia": stores, "serverRendered": True}))
    return (
        f"<html><body>{body}"
        f'<script type="application/json" id="__NUXT_DATA__">{payload}</script></body></html>'
    )


def image(sha: str, position: int) -> dict:
    return {
        "position": position,
        "images": [
            {"format": 0, "storagePath": f"https://images.wk-cdn.it/{sha}//original"},
            {"format": 1, "storagePath": f"https://images.wk-cdn.it/{sha}/webp/640x480.webp"},
            {"format": 3, "storagePath": f"https://images.wk-cdn.it/{sha}/webp/1280x960.webp"},
        ],
    }


def search_page(cards: list[dict], count: int) -> str:
    return nuxt_page({"realEstateListingStoreId": {"listingCount": count, "realEstateList": cards, "pageIdx": 1}})


SALE_CARD = {"realEstateID": 101, "url": "/annuncio/101", "contractType": "SALE",
             "priceSale": 135000, "priceRent": 0, "price": 135000}
# An auction card's "price" is the minimum offer; the listing's price is the base.
AUCTION_CARD = {"realEstateID": 202, "url": "/annuncio/202", "contractType": "AUCTION",
                "priceSale": 79000, "auctionBasePrice": 79000, "priceFrom": 60000, "price": 60000}
HIDDEN_PRICE_CARD = {"realEstateID": 303, "url": "/annuncio/303", "contractType": "SALE",
                     "priceSale": 250000, "price": 250000, "reservedPrice": True}

LABELS = (
    '<div><p class="tw-mb-0 tw-text-12">Stato</p>'
    '<span class="tw-text tw-font-medium"><span>Buone condizioni</span></span></div>'
    '<div><p class="tw-mb-0 tw-text-12">Ascensore</p><span class="tw-text tw-font-medium">No</span></div>'
)


def detail(**overrides) -> dict:
    real_estate = {
        "id": 101,
        "sale": True,
        "rent": False,
        "price": 135000,
        "sqM": 36,
        "rooms": 2,
        "bedrooms": 1,
        "bathrooms": 1,
        "floor": "1",
        "buildingFloors": 5,
        "buildingYear": 1970,
        "typologyName": "Appartamento",
        "description": "Bilocale luminoso al primo piano di uno stabile senza ascensore.",
        "publishAddress": True,
        "publishMap": True,
        "streetName": "Via Dante Alighieri",
        "latitude": 41.1217,
        "longitude": 16.8640,
        "cityName": "Bari",
        "zoneName": "Marconi, Libertà",
        "districtName": "Libertà",
        "energyClassType2015Name": "A4",
        "hasBalconies": True,
        "balconies": 1,
        "lift": False,
        "box": 1,
        "garden": False,
        "annualExpenses": 1200,
        "date": "2026-10-13",
        "reImages": [image("bbb", 1), image("aaa", 0)],
        "rePlanimetries": [image("ppp", 0)],
    }
    real_estate.update(overrides)
    return real_estate


def detail_page(real_estate: dict, title="Bilocale in Vendita, Via Dante Alighieri, Bari") -> str:
    return nuxt_page(
        {"realEstateDetailsStoreId": {"realEstate": real_estate, "title": title,
                                      "place": {"provinceAcronym": "BA"}}},
        body=LABELS,
    )


AUCTION = dict(
    id=202, auction=True, price=79000, auctionBasePrice=79000, auctionMinimumOffer=60000,
    auctionMinimumBid=2000, auctionDate="2027-01-22T16:30:00.000+0000",
    auctionSubmissionDeadline="2027-01-15T12:00:00.000+0000", auctionCourtName="Tribunale di Bari",
    auctionProcedureNumber=431, auctionProcedureYear=2022,
    auctionProcedureTypologyName="ESECUZIONE IMMOBILIARE", auctionSaleModeName="Asincrona telematica",
    auctionPvpBookingLink="https://pvp.giustizia.it/pvp/it/prenotazione_visita.page?idVendita=1",
    auctionPvpPublicationDate="2026-10-09T02:00:00.000+0000",
    attachments=[{"fileName": "avviso.pdf", "url": "https://document.wk-cdn.it/pvp/1/a.pdf"}],
)


def _spider():
    return WikicasaSpider(rate_limiter=RateLimiter(requests_per_minute=600))


# ------------------------------------------------------------------ search


async def test_search_cards_give_urls_and_comparable_prices():
    spider = _spider()
    html = search_page([SALE_CARD, AUCTION_CARD, HIDDEN_PRICE_CARD], count=60)
    assert await spider.parse_search_results_with_prices(html) == [
        ("https://www.wikicasa.it/annuncio/101", 135000.0),
        ("https://www.wikicasa.it/annuncio/202", 79000.0),  # base price, not the minimum offer
        ("https://www.wikicasa.it/annuncio/303", None),  # "trattativa riservata"
    ]
    assert await spider.get_total_pages(html) == 3  # 60 listings, 25 per page


async def test_search_urls_per_section_and_page():
    spider = _spider()
    params = SearchParams(city="San Giovanni Rotondo")
    assert await spider.build_search_url(params, 1) == "https://www.wikicasa.it/vendita-case/san-giovanni-rotondo/"
    spider._section = "asta-case"
    assert await spider.build_search_url(params, 3) == "https://www.wikicasa.it/asta-case/san-giovanni-rotondo/?p=3"


async def test_a_page_without_payload_has_no_cards():
    spider = _spider()
    assert await spider.parse_search_results_with_prices("<html>Cloudflare</html>") == []
    assert await spider.get_total_pages("<html></html>") == 1


async def test_run_walks_sales_then_auctions(monkeypatch):
    spider = _spider()
    pages = {
        "https://www.wikicasa.it/vendita-case/bari/": search_page([SALE_CARD], count=1),
        "https://www.wikicasa.it/asta-case/bari/": search_page([AUCTION_CARD], count=1),
        "https://www.wikicasa.it/annuncio/101": detail_page(detail()),
        "https://www.wikicasa.it/annuncio/202": detail_page(detail(**AUCTION)),
    }

    async def fake_fetch(url, retries=3, *, not_found_ok=True):
        return pages.get(url)

    monkeypatch.setattr(spider, "fetch", fake_fetch)
    items = [i async for i in spider.run(SearchParams(city="bari"))]
    assert sorted(i.source_id for i in items) == ["101", "202"]
    assert spider.listings_seen == 2
    assert spider.coverage_complete


async def test_a_failed_auction_list_keeps_the_sales_but_not_full_coverage(monkeypatch):
    spider = _spider()
    pages = {
        "https://www.wikicasa.it/vendita-case/bari/": search_page([SALE_CARD], count=1),
        "https://www.wikicasa.it/annuncio/101": detail_page(detail()),
    }

    async def fake_fetch(url, retries=3, *, not_found_ok=True):
        return pages.get(url)

    monkeypatch.setattr(spider, "fetch", fake_fetch)
    items = [i async for i in spider.run(SearchParams(city="bari"))]
    assert [i.source_id for i in items] == ["101"]
    assert not spider.coverage_complete  # vanished listings must not be inferred


# ------------------------------------------------------------------ detail


async def test_detail_fields():
    item = await _spider().parse_listing("https://www.wikicasa.it/annuncio/101", detail_page(detail()))
    assert item.source_id == "101"
    assert item.source_url == "https://www.wikicasa.it/annuncio/101"
    assert item.title == "Bilocale in Vendita, Via Dante Alighieri, Bari"
    assert (item.price, item.area_sqm, item.rooms, item.bedrooms, item.bathrooms) == (135000, 36, 2, 1, 1)
    assert (item.floor, item.total_floors, item.year_built) == ("1", 5, 1970)
    assert (item.city, item.zone, item.province) == ("bari", "Marconi, Libertà", "BA")
    assert item.address == "Via Dante Alighieri"
    assert (item.lat, item.lng) == (41.1217, 16.8640)
    assert item.energy_class == "A4"
    assert item.condition == "buono"  # from the rendered "Buone condizioni"
    assert item.condominium_fees == 100  # 1200 a year
    assert item.publication_date == "2026-10-13"
    assert item.listing_type == "sale" and item.property_type == "apartment"
    assert item.is_auction is False and item.auction is None


async def test_detail_photos_in_order_at_the_large_size():
    item = await _spider().parse_listing("u", detail_page(detail()))
    assert item.images == [
        "https://images.wk-cdn.it/aaa/webp/1280x960.webp",
        "https://images.wk-cdn.it/bbb/webp/1280x960.webp",
    ]
    assert item.floor_plans == ["https://images.wk-cdn.it/ppp/webp/1280x960.webp"]


async def test_amenities_ticked_or_stated_in_the_description():
    item = await _spider().parse_listing("u", detail_page(detail()))
    assert item.has_balcony is True
    assert item.has_garage is True  # box: 1
    assert item.has_elevator is False  # unticked, and "senza ascensore"
    assert item.has_garden is None  # unticked, never mentioned: unknown
    assert item.has_terrace is None


async def test_hidden_location_and_address_are_not_guessed():
    item = await _spider().parse_listing(
        "u", detail_page(detail(publishMap=False, publishAddress=False))
    )
    assert (item.lat, item.lng) == (None, None)  # the payload has the city centre
    assert item.address is None


async def test_placeholders_are_unknown():
    item = await _spider().parse_listing(
        "u", detail_page(detail(energyClassType2015Name="PENDING", reservedPrice=True, annualExpenses=0))
    )
    assert item.energy_class is None
    assert item.price is None
    assert item.condominium_fees is None


async def test_rentals():
    item = await _spider().parse_listing("u", detail_page(detail(sale=False, rent=True, price=900)))
    assert item.listing_type == "rent"
    assert item.price == 900


async def test_auction_detail_carries_the_sale_data():
    item = await _spider().parse_listing("u", detail_page(detail(**AUCTION), title="Appartamento in Asta, Bari"))
    assert item.is_auction is True
    assert item.price == 79000  # base price
    assert item.publication_date == "2026-10-09"  # publication on the PVP
    assert item.auction == {
        "date": "2027-01-22T16:30",  # wall-clock time, as the site shows it
        "base_price": 79000,
        "minimum_offer": 60000,
        "minimum_raise": 2000,
        "offer_deadline": "2027-01-15T12:00",
        "court": "Tribunale di Bari",
        "procedure": "431/2022",
        "procedure_type": "ESECUZIONE IMMOBILIARE",
        "sale_mode": "Asincrona telematica",
        "pvp_url": "https://pvp.giustizia.it/pvp/it/prenotazione_visita.page?idVendita=1",
        "documents": [{"name": "avviso.pdf", "url": "https://document.wk-cdn.it/pvp/1/a.pdf"}],
    }


async def test_a_page_without_listing_data_is_a_parse_error():
    with pytest.raises(ValueError):
        await _spider().parse_listing("u", "<html>redirected home</html>")
