"""Parser contract tests on synthetic HTML.

The fixtures mimic the real page structures (casa.it ``__NEXT_DATA__``
``pdp`` object, vistocasa ALL-CAPS label stream and fancybox anchors,
remax Next.js RSC flight chunks) without storing third-party pages in
the repo. They lock the parsing
contract so refactors can't silently change extracted fields; a live
smoke run is still what catches the *sites* changing.
"""

import json

import pytest

from scraper.spiders.base import SearchParams
from scraper.spiders.casa import CasaSpider
from scraper.spiders.immobiliare import ImmobiliareSpider
from scraper.spiders.remax import RemaxSpider
from scraper.spiders.vistocasa import VistocasaSpider, _build_label_map, _strip_tags
from scraper.utils.rate_limiter import RateLimiter


def _spider(cls):
    return cls(rate_limiter=RateLimiter(requests_per_minute=600))


# --------------------------------------------------------------------- casa


def casa_page(pdp: dict, body: str = "") -> str:
    data = {"props": {"pageProps": {"pdp": pdp}}}
    return (
        "<html><head></head><body>"
        "<h1>Trilocale in Vendita in Via Sparano a Bari</h1>"
        f"{body}"
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        "</body></html>"
    )


CASA_PDP = {
    "modified": "13 Aprile 2026",
    "media": {
        "hostImages": "https://images-1.casa.it/",
        "gallery": [
            {"mediaid": "0/aa/bb/cc/111.jpg", "type": "photo"},
            {"mediaid": "0/aa/bb/cc/222.jpg", "type": "photo"},
            {"mediaid": "0/aa/bb/cc/333.jpg", "type": "floorplan"},
        ],
    },
    "address": {
        "street": "Via Sparano 10",
        "town": "Bari",
        "zone": "Murat",
        "province": "BA",
        "lat": "41.1240",
        "lon": "16.8690",
    },
}


async def test_casa_images_use_listing_segment():
    item = await _spider(CasaSpider).parse_listing(
        "https://www.casa.it/immobili/53743664/", casa_page(CASA_PDP)
    )
    assert item.images == [
        "https://images-1.casa.it/800x600/listing/0/aa/bb/cc/111.jpg",
        "https://images-1.casa.it/800x600/listing/0/aa/bb/cc/222.jpg",
    ]


async def test_casa_floorplan_type_goes_to_floor_plans():
    item = await _spider(CasaSpider).parse_listing(
        "https://www.casa.it/immobili/53743664/", casa_page(CASA_PDP)
    )
    assert item.floor_plans == ["https://images-1.casa.it/800x600/listing/0/aa/bb/cc/333.jpg"]


async def test_casa_address_and_geo_from_next_data():
    item = await _spider(CasaSpider).parse_listing(
        "https://www.casa.it/immobili/53743664/", casa_page(CASA_PDP)
    )
    assert item.source_id == "53743664"
    assert item.city == "bari"
    assert item.zone == "Murat"
    assert item.address == "Via Sparano 10"
    assert (item.lat, item.lng) == (41.124, 16.869)
    assert item.publication_date == "2026-04-13"


CASA_FEATURES = {
    "featureLists": [{
        "label": "Caratteristiche",
        "items": [
            {"label": "Ascensore", "values": ["no"]},
            {"label": "Posto auto", "values": [{"main": 1, "integrative": " scoperto"}]},
            {"label": "Altre caratteristiche", "values": ["balcone", "portineria"],
             "displayType": "tag"},
        ],
    }]
}
# Sidebar facet + SEO text that used to flip every flag to True.
CASA_NOISE = "<aside>Filtri: Con giardino · Con terrazzo · Ascensore</aside>"


async def test_casa_flags_from_structured_features_not_page_noise():
    pdp = {**CASA_PDP, "features": CASA_FEATURES}
    item = await _spider(CasaSpider).parse_listing(
        "https://www.casa.it/immobili/1/", casa_page(pdp, body=CASA_NOISE)
    )
    assert item.has_elevator is False  # structured "no", despite the facet
    assert item.has_garage is True     # "Posto auto: 1"
    assert item.has_balcony is True    # tag
    assert item.has_garden is None     # only in the sidebar → unknown
    assert item.has_terrace is None


async def test_casa_flags_fall_back_to_description():
    pdp = {**CASA_PDP, "features": {"featureLists": []},
           "description": None}
    html = casa_page(pdp, body=CASA_NOISE).replace(
        "<h1>", '<div class="description">Villa con giardino privato, senza ascensore</div><h1>'
    )
    item = await _spider(CasaSpider).parse_listing("https://www.casa.it/immobili/1/", html)
    assert item.has_garden is True
    assert item.has_elevator is False


async def test_casa_total_pages_from_result_count():
    # Real page count, uncapped: the run applies max_pages and flags the
    # truncation, so coverage can be reported honestly.
    spider = _spider(CasaSpider)
    assert await spider.get_total_pages("<div>875 annunci</div>") == 44
    assert await spider.get_total_pages("<div>5.000 annunci</div>") == 250


async def test_vistocasa_total_pages_prefers_result_count_over_strip():
    # The strip renders a 15-page window; trusting it capped coverage at 12%.
    html = '<div class="paginazione"><a>1</a><a>2</a><a>15</a></div> 1493 risultati'
    assert await _spider(VistocasaSpider).get_total_pages(html) == 125


# ---------------------------------------------------------------- vistocasa

VISTO_DETAIL = """
<html><head>
<meta property="og:title" content="Appartamento 2 vani - Agenzia Vistocasa Bari Libertà">
<meta property="og:description" content="Situato in via Principe Amedeo, accogliente bivani">
</head><body>
<h1>Bari Libertà - Appartamento 2 vani in Vendita</h1>
<ul>
 <li><span>CONTRATTO</span> Vendita</li>
 <li><span>TIPOLOGIA</span> Appartamento</li>
 <li><span>SUPERFICIE</span> 50 m<sup>2</sup></li>
 <li><span>LOCALI</span> 2</li>
 <li><span>PIANO</span> 2</li>
 <li><span>ASCENSORE</span> si</li>
 <li class="prezzo"><span>PREZZO</span> 50.000 €</li>
 <li><span>SPESE CONDOMINIALI</span> 50 €</li>
 <li><span>STATO</span> Da rimodernare</li>
 <li><span>CERTIFICAZIONE ENERGETICA</span> G</li>
</ul>
<p>Conoscere il corretto prezzo del tuo immobile è il primo step</p>
<img src="../immobili/fotoimmobile9517/1.jpg">
<img src="../immobili/fotoimmobile9517/f55882e9-1b3f-48e6-bbdf-446ea4c3cb34.jpg">
<img src="../immobili/fotoimmobile9999/1.jpg">
<a data-fancybox="planimetria" href="../immobili/fotoimmobile9517/PLANIMETRIA PIANO TERRA.jpg">p</a>
</body></html>
"""


@pytest.fixture
def no_network(monkeypatch):
    """parse_listing HEADs the first image for a publication date; keep
    unit tests offline."""
    async def fake(self, url):
        return "2026-04-24"
    monkeypatch.setattr(VistocasaSpider, "_pub_date_from_image", fake)


async def test_vistocasa_label_values(no_network):
    item = await _spider(VistocasaSpider).parse_listing(
        "https://www.vistocasa.com/it/immobile.aspx?ArticoliId=9517", VISTO_DETAIL
    )
    assert item.price == 50000.0
    assert item.area_sqm == 50.0
    assert item.rooms == 2
    assert item.floor == "2"
    assert item.has_elevator is True
    assert item.condominium_fees == 50.0
    assert item.condition == "Da rimodernare"
    assert item.energy_class == "G"
    assert item.listing_type == "sale"
    assert item.city == "bari"
    assert item.zone == "Libertà"


async def test_vistocasa_lowercase_prezzo_in_prose_is_not_a_label(no_network):
    # "prezzo" in the CTA paragraph must not override the real PREZZO.
    item = await _spider(VistocasaSpider).parse_listing(
        "https://www.vistocasa.com/it/immobile.aspx?ArticoliId=9517", VISTO_DETAIL
    )
    assert item.price == 50000.0


async def test_vistocasa_images_and_floor_plans(no_network):
    item = await _spider(VistocasaSpider).parse_listing(
        "https://www.vistocasa.com/it/immobile.aspx?ArticoliId=9517", VISTO_DETAIL
    )
    base = "https://www.vistocasa.com/immobili/fotoimmobile9517"
    # Only this listing's folder; GUID and integer names both accepted.
    assert item.images == [f"{base}/1.jpg", f"{base}/f55882e9-1b3f-48e6-bbdf-446ea4c3cb34.jpg"]
    assert item.floor_plans == [f"{base}/PLANIMETRIA%20PIANO%20TERRA.jpg"]
    assert item.publication_date == "2026-04-24"


def test_vistocasa_label_map_first_occurrence_wins():
    labels = _build_label_map(_strip_tags("PREZZO 50.000 € LOCALI 2 PREZZO 99.000 €"))
    assert labels["PREZZO"] == "50.000 €"
    assert labels["LOCALI"] == "2"


async def test_vistocasa_search_card_prices():
    html = (
        '<a href="immobile.aspx?ArticoliId=111">Bari</a> Rif. X 149.000 € 3 locali '
        '<a href="immobile.aspx?ArticoliId=222">Bari</a> Rif. Y 1.250.000 â‚¬ villa '
        '<a href="immobile.aspx?ArticoliId=333">Bari</a> Trattativa riservata'
    )
    pairs = await _spider(VistocasaSpider).parse_search_results_with_prices(html)
    by_id = {url.rsplit("=", 1)[1]: price for url, price in pairs}
    assert by_id == {"111": 149000.0, "222": 1250000.0, "333": None}


# -------------------------------------------------------------------- remax


def rsc_page(flight: str, ld: list[dict] = (), head: str = "") -> str:
    """App Router page: the flight split across two push() chunks (the
    split lands mid-row on purpose), JSON-escaped like Next.js does."""
    mid = len(flight) // 2
    pushes = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>"
        for part in (flight[:mid], flight[mid:])
    )
    lds = "".join(f'<script type="application/ld+json">{json.dumps(d)}</script>' for d in ld)
    return f"<html><head>{head}<title>Villa in vendita a Bari | REMAX</title></head><body>{lds}{pushes}</body></html>"


REMAX_URL = "https://oltre.remax.it/vendita-villa-o-villino/bari/japigia-36681014-42"
# Multi-byte characters: the T-row length prefix counts UTF-8 bytes.
REMAX_DESC = "<p>Villa con balcone, città più bella.<br>Ultimo piano</p>"
REMAX_PROPERTY = {
    "id": "a69a9932", "code": "36681014-42", "propertyType": "villa_o_villino",
    "macroCategory": "residenziale", "contractType": "vendita", "price": 1290000,
    "isConfidential": False, "totalArea": 195, "rooms": 5, "bedrooms": 4, "bathrooms": 2,
    "floor": "piano_terra", "totalFloors": 2, "city": "Bari", "province": "Bari",
    "neighborhood": "San Giorgio", "address": "Via Giovine 61",
    "latitude": 41.1009, "longitude": 16.9493, "publishedAt": "2026-04-24T00:00:00.000Z",
    "description": "$55", "energyClass": "a4", "conservationState": "da_ristrutturare",
    "heating": "autonomo", "constructionYear": 1975, "condominiumFees": 80,
    "hasElevator": False, "hasTerrace": False, "hasGarden": True,
    "hasGarage": False, "hasBox": True, "hasParking": None,
    "photos": [
        {"url": "https://cdn.test/p/2.jpg", "order": 2, "isFloorPlan": False},
        {"url": "https://cdn.test/p/plan.jpg", "order": 3, "isFloorPlan": True},
        {"url": "https://cdn.test/p/1.jpg", "order": 1, "isFloorPlan": False},
    ],
}


def remax_detail(prop: dict = REMAX_PROPERTY) -> str:
    desc_len = len(REMAX_DESC.encode("utf-8"))
    similar = {"code": "99999-1", "price": 1}  # a "similar listings" card
    flight = (
        '0:["$","html",null,{}]\n'
        f'53:["$","$L60",null,{{"property":{json.dumps(similar)}}}]\n'
        f"55:T{desc_len:x},{REMAX_DESC}"
        f'56:["$","$L54",null,{{"property":{json.dumps(prop)}}}]\n'
        '57:["$","div",null,{"property":"$L58"}]\n'
    )
    return rsc_page(flight)


async def test_remax_detail_structured_fields():
    item = await _spider(RemaxSpider).parse_listing(REMAX_URL, remax_detail())
    assert item.source_id == "36681014-42"  # the listing, not the similar card
    assert (item.price, item.area_sqm, item.rooms, item.bedrooms, item.bathrooms) == (
        1290000.0, 195.0, 5, 4, 2)
    assert item.property_type == "villa"
    assert item.listing_type == "sale"
    assert item.floor == "T"  # floor-filter vocabulary
    assert item.energy_class == "A4"
    assert item.condition == "da_ristrutturare"
    assert item.year_built == 1975
    assert item.condominium_fees == 80.0
    assert (item.city, item.zone, item.address) == ("bari", "San Giorgio", "Via Giovine 61")
    assert (item.lat, item.lng) == (41.1009, 16.9493)
    assert item.publication_date == "2026-04-24"
    assert item.title == "Villa in vendita a Bari"


async def test_remax_description_text_row_is_sliced_by_bytes():
    item = await _spider(RemaxSpider).parse_listing(REMAX_URL, remax_detail())
    # Exactly the referenced row: no bleed into row 56's JSON.
    assert item.description == "Villa con balcone, città più bella.\nUltimo piano"


async def test_remax_photos_ordered_and_floor_plans_split():
    item = await _spider(RemaxSpider).parse_listing(REMAX_URL, remax_detail())
    assert item.images == ["https://cdn.test/p/1.jpg", "https://cdn.test/p/2.jpg"]
    assert item.floor_plans == ["https://cdn.test/p/plan.jpg"]


async def test_remax_flags_structured_first_then_description():
    item = await _spider(RemaxSpider).parse_listing(REMAX_URL, remax_detail())
    assert item.has_elevator is False  # unticked, description silent
    assert item.has_balcony is True    # no structured field, "balcone" in text
    assert item.has_garage is True     # hasBox
    assert item.has_garden is True
    assert item.has_terrace is False


async def test_remax_confidential_price_is_unknown():
    item = await _spider(RemaxSpider).parse_listing(
        REMAX_URL, remax_detail({**REMAX_PROPERTY, "isConfidential": True})
    )
    assert item.price is None


async def test_remax_missing_payload_is_a_parse_error():
    with pytest.raises(ValueError):
        await _spider(RemaxSpider).parse_listing(REMAX_URL, rsc_page('0:["$","html",null,{}]\n'))


async def test_remax_search_urls_card_prices_and_pages():
    urls = [
        "https://oltre.remax.it/vendita-villa-o-villino/bari/japigia-36681014-42",
        "https://acqua.remax.it/vendita-appartamento/bari/murat-20031073-355",
    ]
    item_list = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": u} for i, u in enumerate(urls)
    ]}
    cards = [{"code": "36681014-42", "price": 1290000, "isConfidential": False},
             {"code": "20031073-355", "price": 990000, "isConfidential": True}]
    flight = "".join(
        f'{60 + i}:["$","div","k{i}",{{"children":["$","$L67",null,{{"property":{json.dumps(c)}}}]}}]\n'
        for i, c in enumerate(cards)
    ) + '72:["$","$L73","pagination",{"currentPage":1,"totalPages":37}]\n'
    html = rsc_page(flight, ld=[item_list])
    spider = _spider(RemaxSpider)

    assert await spider.parse_search_results_with_prices(html) == [(urls[0], 1290000.0), (urls[1], None)]
    assert await spider.get_total_pages(html) == 37
    assert [spider._extract_source_id_from_url(u) for u in urls] == ["36681014-42", "20031073-355"]


async def test_remax_total_pages_falls_back_to_result_count():
    html = rsc_page("", head='<meta name="description" content="437 case in vendita a Bari.">')
    assert await _spider(RemaxSpider).get_total_pages(html) == 37  # ceil(437 / 12)


async def test_remax_search_url_scheme():
    spider = _spider(RemaxSpider)
    assert await spider.build_search_url(SearchParams(city="bari"), 1) == "https://www.remax.it/vendita-case/bari"
    assert await spider.build_search_url(SearchParams(city="Reggio Emilia", listing_type="rent"), 3) == (
        "https://www.remax.it/affitto-case/reggio-emilia?page=3")


# -------------------------------------------------------------- immobiliare


def _immobiliare_result(listing_id: int, contract: str) -> dict:
    return {
        "seo": {"url": f"https://www.immobiliare.it/annunci/{listing_id}/"},
        "realEstate": {
            "id": listing_id,
            "contract": contract,
            "type": "auction" if contract == "auction" else "ad",
            "title": "Appartamento",
            "properties": [{
                "isMain": True,
                "caption": "Appartamento a Bari",
                "location": {"city": "Bari", "latitude": 41.12, "longitude": 16.87},
                "price": {"value": 120000},
            }],
        },
    }


def test_immobiliare_structured_auction_flag():
    data = {"results": [_immobiliare_result(1, "auction"), _immobiliare_result(2, "sale")]}
    items = _spider(ImmobiliareSpider)._extract_items(data, SearchParams())
    assert {i.source_id: i.is_auction for i in items} == {"1": True, "2": False}
