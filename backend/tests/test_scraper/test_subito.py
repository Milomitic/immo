"""SubitoSpider on synthetic search pages shaped like the site's __NEXT_DATA__."""

import json

from scraper.spiders.base import SearchParams
from scraper.spiders.subito import SubitoSpider
from scraper.utils.rate_limiter import RateLimiter


def feature(key, value):
    return {"values": [{"key": str(key), "value": value}]}


def card(ad_id: int, **features) -> dict:
    base = {
        "price": feature(250000, "250000 €"),
        "size": feature(90, "90 mq"),
        "room": feature(3, "3"),
        "bathrooms": feature(2, "2"),
        "floor": feature(3, "2"),
        "heating": feature(2, "Autonomo"),
        "building_condition": feature(20, "Buono / Abitabile"),
        "energy_class": feature(100, "A4"),
        "elevator": feature(1, "Sì"),
        "balcony": feature(0, "No"),
        "parking": feature(1, "Box privato"),
    }
    base.update(features)
    return {
        "kind": "AdItem",
        "subject": "Trilocale Poggiofranco",
        "body": "Luminoso trilocale con terrazzo, vicino ai servizi.",
        "date": "2026-10-13 18:38:23",
        "images": [{"cdnBaseUrl": f"https://images.sbito.it/api/v1/sbt-ads-images-pro/images/f6/{ad_id}"}],
        "features": {f"/{k}": v for k, v in base.items() if v is not None},
        "advertiser": {"company": False, "type": 0},
        "geo": {"town": {"value": "Bari"}, "city": {"shortName": "BA"}},
        "urls": {"default": f"https://www.subito.it/appartamenti/trilocale-poggiofranco-bari-{ad_id}.htm"},
    }


def search_page(cards: list[dict], total: int, pages: int | None = None) -> str:
    items = {"total": total, "originalList": cards,
             "galleryList": [card(999, price=feature(1, "1 €"))]}  # paid placements: ignored
    if pages is not None:
        items["totalPages"] = pages
    data = {"props": {"pageProps": {"initialState": {"items": items}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def _spider():
    return SubitoSpider(rate_limiter=RateLimiter(requests_per_minute=600))


async def test_search_url_per_town_category_and_page():
    spider = _spider()
    spider._area = ("puglia", "bari", "molfetta")
    params = SearchParams(city="Molfetta")
    assert await spider.build_search_url(params, 1) == (
        "https://www.subito.it/annunci-puglia/vendita/appartamenti/bari/molfetta/"
    )
    spider._category, spider._listing_type = "ville-singole-e-a-schiera", "rent"
    assert await spider.build_search_url(params, 2) == (
        "https://www.subito.it/annunci-puglia/affitto/ville-singole-e-a-schiera/bari/molfetta/?o=2"
    )


async def test_total_pages():
    spider = _spider()
    assert await spider.get_total_pages(search_page([], total=893, pages=30)) == 30
    assert await spider.get_total_pages(search_page([], total=61)) == 3
    assert await spider.get_total_pages("<html>blocked</html>") == 1


async def test_cards_become_listings():
    spider = _spider()
    assert await spider.parse_search_results_with_prices(search_page([card(659927771)], total=1)) == [
        ("https://www.subito.it/appartamenti/trilocale-poggiofranco-bari-659927771.htm", 250000.0)
    ]
    item = spider._parsed["https://www.subito.it/appartamenti/trilocale-poggiofranco-bari-659927771.htm"]
    assert item.source_portal == "subito" and item.source_id == "659927771"
    assert (item.price, item.area_sqm, item.rooms, item.bathrooms, item.floor) == (250000, 90, 3, 2, "2")
    assert (item.city, item.province, item.lat, item.address) == ("bari", "BA", None, None)
    assert item.description.startswith("Luminoso trilocale")
    assert item.publication_date == "2026-10-13"
    assert (item.heating, item.condition, item.energy_class) == ("Autonomo", "buono", "A4")
    assert item.images == [
        "https://images.sbito.it/api/v1/sbt-ads-images-pro/images/f6/659927771?rule=gallery-desktop-2x-auto"
    ]
    assert item.raw_data == {"advertiser": "privato"}


async def test_amenities_are_the_sellers_answers_then_the_description():
    spider = _spider()
    await spider.parse_search_results_with_prices(search_page([card(1)], total=1))
    item = next(iter(spider._parsed.values()))
    assert item.has_elevator is True
    assert item.has_balcony is False  # an explicit "No"
    assert item.has_garage is True  # "Box privato"
    assert item.has_terrace is True  # no field: from the description
    assert item.has_garden is None  # neither


async def test_placeholders_and_houses():
    spider = _spider()
    spider._category = "ville-singole-e-a-schiera"
    cards = [card(2, energy_class=feature(0, "Non disponibile"), parking=feature(0, "Nessuno"), price=None)]
    cards[0]["subject"] = "Casa con giardino"
    await spider.parse_search_results_with_prices(search_page(cards, total=1))
    item = next(iter(spider._parsed.values()))
    assert item.energy_class is None
    assert item.has_garage is False
    assert item.price is None
    assert item.property_type == "villa"


async def test_run_never_opens_a_listing_and_only_reports_known_ads(monkeypatch):
    spider = _spider()
    requested = []
    pages = {
        "https://www.subito.it/annunci-puglia/vendita/appartamenti/bari/bari/":
            search_page([card(1), card(2)], total=3, pages=2),
        "https://www.subito.it/annunci-puglia/vendita/appartamenti/bari/bari/?o=2":
            search_page([card(3)], total=3, pages=2),
        "https://www.subito.it/annunci-puglia/vendita/ville-singole-e-a-schiera/bari/bari/":
            search_page([], total=0),
    }

    async def fake_fetch(url, retries=3, *, not_found_ok=True):
        requested.append(url)
        return pages.get(url)

    monkeypatch.setattr(spider, "fetch", fake_fetch)
    items = [i async for i in spider.run(SearchParams(city="Bari", known_source_ids={"2"}))]

    assert sorted(i.source_id for i in items) == ["1", "3"]
    assert spider.known_skipped_ids == ["2"]
    assert spider.observed_prices == {"2": 250000.0}
    assert spider.listings_seen == 3
    assert spider.coverage_complete
    assert all("/annunci-puglia/" in u for u in requested)  # search pages only
    assert len(requested) == 3


async def test_unmapped_city_is_an_explicit_failure():
    spider = _spider()
    items = [i async for i in spider.run(SearchParams(city="Trieste"))]
    assert items == []
    assert not spider.coverage_complete
    assert "Trieste" in spider.errors[0]["message"]
