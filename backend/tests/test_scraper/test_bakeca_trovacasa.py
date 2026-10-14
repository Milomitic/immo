"""BakecaSpider and TrovacasaSpider on synthetic pages shaped like the sites'."""

import json

from scraper.spiders.bakeca import BakecaSpider
from scraper.spiders.base import SearchParams
from scraper.spiders.trovacasa import TrovacasaSpider
from scraper.utils.html_extract import fix_mojibake
from scraper.utils.rate_limiter import RateLimiter


def _spider(cls):
    return cls(rate_limiter=RateLimiter(requests_per_minute=600))


# ------------------------------------------------------------------- bakeca


def residence(listing_id: str, town: str = "Bari", **extra) -> dict:
    ld = {
        "@context": "https://schema.org/",
        "@type": ["Product", "SingleFamilyResidence"],
        "url": f"https://bari.bakeca.it/dettaglio/vendita-case/appartamento-di-137-msup2-con-4-locali-in-vendita-a-bari-{listing_id}?from-premium",
        "name": "Appartamento di 137 m&sup2; con 4 locali in vendita a Bari",
        "description": "Quadrilocale al sesto piano con ascensore, nella citt&agrave; di Bari &hellip;",
        "offers": {"@type": "Offer", "price": "233000", "seller": {"name": "Dove.it"}},
        "address": {"addressLocality": town},
        "geo": {"latitude": 41.1262, "longitude": 16.8511},
    }
    ld.update(extra)
    return ld


def bakeca_page(lds: list[dict], body: str = "") -> str:
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(ld)}</script>' for ld in lds)
    return f"<html><head>{scripts}</head><body>{body}</body></html>"


async def test_bakeca_search_keeps_the_towns_cards_with_prices():
    spider = _spider(BakecaSpider)
    params = SearchParams(city="Bari")
    assert await spider.build_search_url(params, 1) == "https://bari.bakeca.it/annunci/vendita-case/"
    assert await spider.build_search_url(params, 3) == "https://bari.bakeca.it/annunci/vendita-case/page/3/"
    html = bakeca_page([residence("32p9297929970"), residence("yprw297206482", town="Acquaviva delle Fonti")],
                       body="<p>764 annunci</p>")
    assert await spider.parse_search_results_with_prices(html) == [(
        "https://bari.bakeca.it/dettaglio/vendita-case/appartamento-di-137-msup2-con-4-locali-in-vendita-a-bari-32p9297929970",
        233000.0,
    )]
    assert await spider.get_total_pages(html) == 31  # 764 / 25
    assert spider._extract_source_id_from_url(
        "https://bari.bakeca.it/dettaglio/vendita-case/x-di-1-locali-pmrd300002344"
    ) == "pmrd300002344"


async def test_bakeca_detail():
    ld = residence(
        "32p9297929970",
        description="Quadrilocale al sesto piano con ascensore e balcone, nella citt&agrave; di Bari.",
        photo=[{"contentUrl": f"https://static.bakeca.it/immagini/1ed/foto-{i}.jpg"} for i in range(3)],
        amenityFeature=[
            {"name": "Tipo immobile", "value": "Quadrilocale"},
            {"name": "Metri quadri (m2)", "value": 137},
            {"name": "Classe energetica", "value": "G_L90"},
        ],
    )
    meta = ('<div class="meta-block"><span class="meta-label">Quartiere:</span> Marconi, San Cataldo, Libertà </div>'
            '<div class="meta-block"><span class="meta-label">Comune</span> Bari </div>')
    url = ld["url"]
    item = await _spider(BakecaSpider).parse_listing(url, bakeca_page([ld], body=meta))
    assert item.source_id == "32p9297929970"
    assert item.source_url == url.split("?")[0]
    assert item.title == "Appartamento di 137 m² con 4 locali in vendita a Bari"
    assert item.description == "Quadrilocale al sesto piano con ascensore e balcone, nella città di Bari."
    assert (item.price, item.area_sqm, item.rooms) == (233000.0, 137.0, 4)
    assert (item.city, item.zone, item.lat, item.lng) == ("bari", "Marconi, San Cataldo, Libertà", 41.1262, 16.8511)
    assert item.energy_class == "G"
    assert len(item.images) == 3
    assert (item.has_elevator, item.has_balcony, item.has_garden) == (True, True, None)
    assert item.raw_data == {"advertiser": "Dove.it"}


async def test_bakeca_detail_falls_back_to_the_title():
    item = await _spider(BakecaSpider).parse_listing("https://bari.bakeca.it/dettaglio/vendita-case/x-32p9297929970",
                                                     bakeca_page([residence("32p9297929970")]))
    assert (item.area_sqm, item.rooms) == (137.0, 4)  # from "di 137 m² con 4 locali"
    assert item.images == []


# ---------------------------------------------------------------- trovacasa


def card(listing_id: int, title: str, zone: str = "Poggiofranco", tags=("Posto Auto", "Riscaldamento Autonomo"),
         description: str = "Ampio quadrivani luminoso") -> str:
    tag_html = "".join(f'<p class="annuncioTag">{t}</p>' for t in tags)
    return (
        f'<div class="immobileListing__card js_immobileListing_card"><div class="card">'
        f'<div class="holder-image js_slider" data-src-list="A_3127_{listing_id}_1|A_3127_{listing_id}_2"></div>'
        f'<a class="card__title js_link_immobile" href="/annunci/ba-tc-3127-{listing_id}">{title}</a>'
        f'<span class="card__quartiere">{zone}</span>'
        f'<div class="card__infoContainer"><span class="card__info">150 m²</span><span class="card__info">4 locali</span></div>'
        f'<span class="card__price">290.000 €</span><p class="card__description">{description}</p>'
        f'<div class="card__tagContainer">{tag_html}</div></div></div>'
    )


def trovacasa_page(cards: list[str], total: str = "2.970") -> str:
    return f"<html><body><h1>{total} Case in vendita a Bari</h1>{''.join(cards)}</body></html>"


async def test_trovacasa_cards_become_listings():
    spider = _spider(TrovacasaSpider)
    params = SearchParams(city="Bari")
    assert await spider.build_search_url(params, 1) == "https://www.trovacasa.it/case-in-vendita/bari"
    assert await spider.build_search_url(params, 2) == "https://www.trovacasa.it/case-in-vendita/bari?page=2"
    spider._city = "Bari"
    html = trovacasa_page([card(73597816, "Appartamento a Bari via Vitantonio Di Cagno, 6")])
    assert await spider.get_total_pages(html) == 124  # 2970 / 24
    assert await spider.parse_search_results_with_prices(html) == [
        ("https://www.trovacasa.it/annunci/ba-tc-3127-73597816", 290000.0)
    ]
    item = spider._parsed["https://www.trovacasa.it/annunci/ba-tc-3127-73597816"]
    assert item.source_id == "73597816"
    assert (item.price, item.area_sqm, item.rooms) == (290000.0, 150.0, 4)
    assert (item.address, item.zone, item.city, item.lat) == ("via Vitantonio Di Cagno, 6", "Poggiofranco", "bari", None)
    assert item.images == [
        "https://cdn.trovacasa.it/annunci/xxl/A_3127_73597816_1/foto.jpg",
        "https://cdn.trovacasa.it/annunci/xxl/A_3127_73597816_2/foto.jpg",
    ]
    assert item.heating == "Autonomo"
    assert item.has_garage is True  # "Posto Auto" tag
    assert item.is_auction is False


async def test_trovacasa_titles_text_and_auctions():
    spider = _spider(TrovacasaSpider)
    spider._city = "Bari"
    await spider.parse_search_results_with_prices(trovacasa_page([
        card(1, "Appartamento a Bari bari michelangelo signorile,28", zone="",
             description="Bivani â€“ Zona Madonnella, l'immobile Ã¨ luminoso"),
        card(2, "Appartamento all'asta a Bari", tags=("All'asta/Asta giudiziaria",)),
        card(3, "Villa a Bari strada dello Schiamante", tags=()),
    ]))
    items = {i.source_id: i for i in spider._parsed.values()}
    assert items["1"].address == "michelangelo signorile,28"  # the town repeated, dropped
    assert items["1"].zone is None
    assert items["1"].description == "Bivani – Zona Madonnella, l'immobile è luminoso"
    assert items["2"].is_auction is True and items["2"].address is None
    assert items["3"].property_type == "villa"


async def test_trovacasa_run_never_opens_a_listing(monkeypatch):
    spider = _spider(TrovacasaSpider)
    requested = []
    pages = {
        "https://www.trovacasa.it/case-in-vendita/bari": trovacasa_page(
            [card(1, "Appartamento a Bari via Roma, 1"), card(2, "Appartamento a Bari via Sparano, 2")], total="25"),
        "https://www.trovacasa.it/case-in-vendita/bari?page=2": trovacasa_page(
            [card(3, "Appartamento a Bari via Calefati, 3")], total="25"),
    }

    async def fake_fetch(url, retries=3, *, not_found_ok=True):
        requested.append(url)
        return pages.get(url)

    monkeypatch.setattr(spider, "fetch", fake_fetch)
    items = [i async for i in spider.run(SearchParams(city="Bari", known_source_ids={"2"}))]
    assert sorted(i.source_id for i in items) == ["1", "3"]
    assert spider.known_skipped_ids == ["2"]
    assert spider.observed_prices == {"2": 290000.0}
    assert spider.coverage_complete
    assert requested == list(pages)  # search pages only


def test_fix_mojibake():
    assert fix_mojibake("L'immobile Ã¨ proposto â€“ subito") == "L'immobile è proposto – subito"
    assert fix_mojibake("città già corretta") == "città già corretta"
    assert fix_mojibake(None) == ""
    # mixed with text that is fine: each broken sequence on its own
    assert fix_mojibake("Bari â€“ Carbonara, già venduto") == "Bari – Carbonara, già venduto"
    assert fix_mojibake("esterni privati, questa Ã...") == "esterni privati, questa ..."  # cut in the middle
    # never a correct accented capital or a final accent
    assert fix_mojibake("PERCHÉ… scegliere questa città") == "PERCHÉ… scegliere questa città"
    assert fix_mojibake("Âœ¨Dove il tempo rallenta") == "Âœ¨Dove il tempo rallenta"  # would be a control char
    assert fix_mojibake("Bari, LibertÃ\u00a0") == "Bari, Libertà"
