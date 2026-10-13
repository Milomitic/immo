"""Parser contract tests on synthetic HTML.

The fixtures mimic the real page structures (casa.it ``__NEXT_DATA__``
``pdp`` object, vistocasa ALL-CAPS label stream and fancybox anchors)
without storing third-party pages in the repo. They lock the parsing
contract so refactors can't silently change extracted fields; a live
smoke run is still what catches the *sites* changing.
"""

import json

import pytest

from scraper.spiders.casa import CasaSpider
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


async def test_casa_total_pages_from_result_count():
    spider = _spider(CasaSpider)
    assert await spider.get_total_pages("<div>875 annunci</div>") == 44
    assert await spider.get_total_pages("<div>5.000 annunci</div>") == 50  # capped


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
