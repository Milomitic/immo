"""
Vistocasa.com spider.

Vistocasa is an ASP.NET WebForms agency franchise serving the Puglia /
Basilicata regions. Search results live behind ``ricerca.aspx`` and use
classic ``__doPostBack`` for pagination — the page-2 link looks like
``__doPostBack('ctl00$cph$datarpt_paginazione$ctl03$LinkButton1', '')`` so
to navigate forward we POST the form back with that value as
``__EVENTTARGET`` plus the freshly captured ``__VIEWSTATE``. We override
``run()`` because the GET-per-page contract assumed by ``BaseSpider``
doesn't fit a stateful WebForms session.

Detail pages are at ``immobile.aspx?ArticoliId=<id>``. Their structured
data is rendered as uppercase-labelled inline blocks (``>PREZZO 50.000 €
SPESE CONDOMINIALI 50 €<``) — no ``<dt>``/``<dd>`` so we extract via
regex over the raw HTML once.

Coordinates aren't published on the page (would require geocoding). City
and zone are read from the H1 (e.g. "Bari Liberta - Appartamento 2 vani
in Vendita"). Image URLs follow the convention
``/immobili/fotoimmobile<id>/N.jpg`` and the count comes from how many of
those references appear in the gallery markup.
"""

import asyncio
import re
import unicodedata
from collections.abc import AsyncGenerator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.items import ListingItem
from scraper.spiders.base import BaseSpider, SearchParams
from scraper.utils.html_extract import map_property_type, parse_italian_date


# Known label vocabulary. Detail-panel labels are rendered in ALL CAPS on
# the page, which is *also* how we discriminate them from prose: the word
# "prezzo" appears 42 times on a typical listing (CSS class names,
# description text, sidebar CTAs), but "PREZZO" appears exactly once — at
# the price label. So we match case-sensitively and only on the all-caps
# form.
_KNOWN_LABELS = (
    "TIPOLOGIA",
    "SUPERFICIE",
    "LOCALI",
    "VANI",
    "BAGNI",
    "SERVIZI",
    "PIANO",
    "TIPO PROPRIETÀ",
    "TIPO PROPRIETA",
    "ASCENSORE",
    "STATO",
    "RISCALDAMENTO",
    "PREZZO",
    "SPESE CONDOMINIALI",
    "CERTIFICAZIONE ENERGETICA",
    "CLASSE ENERGETICA",
    "DISPONIBILITA",
    "DISPONIBILITÀ",
    "CONTRATTO",
    "ANNO COSTRUZIONE",
    "ANNO DI COSTRUZIONE",
    "RIFERIMENTO",
    "GIARDINO",
    "TERRAZZO",
    "BALCONE",
    "BOX",
)

# Single regex matching any known label as a whole token (case-sensitive,
# longer labels first so "TIPO PROPRIETÀ" wins over a hypothetical "TIPO").
_LABEL_TOKEN_RE = re.compile(
    "(" + "|".join(re.escape(l) for l in sorted(_KNOWN_LABELS, key=len, reverse=True)) + ")"
)


def _strip_tags(html: str) -> str:
    """Collapse HTML to a single-line stream of text suitable for label
    matching. Cheaper than a full BeautifulSoup walk on every detail
    page."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_label_map(stream: str) -> dict[str, str]:
    """Tokenise the stream into ``{normalized_label: value}`` by splitting
    on known labels — each value is the text between two known labels.

    Splitting (rather than regexing per label) means any label can
    terminate any value, which is what we want for the inline layout used
    by vistocasa. **First-write-wins**: the canonical detail panel sits
    near the top of the page, so the first occurrence of a label is the
    real one; later occurrences (sidebar widgets, recent-listings carousel)
    just confuse things.
    """
    parts = _LABEL_TOKEN_RE.split(stream)
    # `re.split` with a capture group yields [pre, label, between, label, between, ...]
    out: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip().upper()
        value = parts[i + 1].strip(" :|;,-").strip()
        if label and value:
            out.setdefault(label, value)
    return out


def _label_lookup(label_map: dict[str, str], *labels: str) -> str | None:
    for label in labels:
        v = label_map.get(label.upper())
        if v:
            return v
    return None


def _parse_price(raw: str | None) -> float | None:
    if not raw:
        return None
    # "50.000 €" / "€ 1.250.000" — Italian thousands separators.
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\d+", raw)
    return int(m.group(0)) if m else None


def _parse_area(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", raw)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


_LISTING_TYPE_HINTS = {
    "vendita": "sale",
    "vendi": "sale",
    "affitto": "rent",
    "locazione": "rent",
}


def _detect_listing_type(*texts: str | None) -> str:
    blob = " ".join(t for t in texts if t).lower()
    for k, v in _LISTING_TYPE_HINTS.items():
        if k in blob:
            return v
    return "sale"


# H1 typically reads "<City> <Zone> - <Type> <N> vani in Vendita"
_H1_RE = re.compile(r"^(.+?)\s*-\s*(.+?)$")


def _split_h1(h1: str) -> tuple[str, str | None, str | None]:
    """Split the H1 into (city_zone_blob, type_phrase). Best-effort."""
    m = _H1_RE.match(h1)
    if not m:
        return h1, None, None
    location = m.group(1).strip()
    rest = m.group(2).strip()
    # location is "City Zone" — first word is the city, rest is the zone.
    parts = location.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:]), rest
    return location, None, rest


# Image URLs use the predictable pattern /immobili/fotoimmobileNNN/k.jpg.
# We pull every reference to one and dedupe — all sizes/thumbnails point at
# the same set, so we just normalise to "/k.jpg" form.
_IMAGE_RE = re.compile(r"/immobili/fotoimmobile(\d+)/(\d+)\.jpg", re.IGNORECASE)


def _extract_images(html: str, base_url: str, source_id: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _IMAGE_RE.finditer(html):
        if m.group(1) != source_id:
            continue
        idx = int(m.group(2))
        url = f"{base_url}/immobili/fotoimmobile{source_id}/{idx}.jpg"
        if url not in seen:
            seen.add(url)
            out.append(url)
    # Sort by file index so the cover image is index 1.
    out.sort(key=lambda u: int(_IMAGE_RE.search(u).group(2)))  # type: ignore[union-attr]
    return out


def _hidden_field(soup: BeautifulSoup, name: str) -> str:
    el = soup.find("input", {"name": name})
    return el.get("value", "") if el else ""


# Pagination postback target template. ctl01 = page 1, ctl03 = page 2,
# ctl05 = page 3, ... so for page N use ctl{2N-1:02d}.
def _postback_target(page: int) -> str:
    n = 2 * page - 1
    return f"ctl00$cph$datarpt_paginazione$ctl{n:02d}$LinkButton1"


class VistocasaSpider(BaseSpider):
    portal_name = "vistocasa"
    base_url = "https://www.vistocasa.com"
    search_url = "https://www.vistocasa.com/it/ricerca.aspx"

    # Detail URLs use a query param, not a path id — override the default
    # numeric-trailing-segment extractor.
    @staticmethod
    def _extract_source_id_from_url(url: str) -> str | None:
        m = re.search(r"[?&][Aa]rticoliId=(\d+)", url)
        return m.group(1) if m else None

    # build_search_url / get_total_pages exist only so the abstract base is
    # satisfied — the real flow lives in `run()` below.
    async def build_search_url(self, params: SearchParams, page: int) -> str:
        return self.search_url

    async def get_total_pages(self, html: str) -> int:
        # Best-effort: parse the page-numbers strip ("1 2 3 ... 15 >>"). The
        # paged catalog yields 12 listings each, capped to ~50 pages.
        soup = BeautifulSoup(html, "lxml")
        nums: list[int] = []
        for el in soup.select("[class*='pagi'] a, [id*='pagi'] a"):
            txt = el.get_text(strip=True)
            if txt.isdigit():
                nums.append(int(txt))
        if nums:
            return min(max(nums), 50)
        # Fallback: parse total result count, divide by 12 per page.
        m = re.search(r"(\d[\d.]*)\s*risultat", html, re.IGNORECASE)
        if m:
            total = int(m.group(1).replace(".", ""))
            return min((total + 11) // 12, 50)
        return 1

    async def parse_search_results(self, html: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for m in re.finditer(r"[Ii]mmobile\.aspx\?ArticoliId=(\d+)", html):
            sid = m.group(1)
            url = f"{self.base_url}/it/immobile.aspx?ArticoliId={sid}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    async def _post_search(self, page: int, vs: str, vsg: str) -> str | None:
        """Issue the ASP.NET __doPostBack to advance to ``page`` and return
        the response HTML. We rely on the same client (and therefore the
        same session cookies) the spider uses elsewhere."""
        await self.rate_limiter.acquire(self.portal_name)
        client = await self._get_client()
        data = {
            "__EVENTTARGET": _postback_target(page),
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": vs,
            "__VIEWSTATEGENERATOR": vsg,
        }
        try:
            resp = await client.post(self.search_url, data=data, timeout=30)
            if resp.status_code != 200:
                return None
            return resp.text
        except Exception:
            return None

    async def run(self, params: SearchParams) -> AsyncGenerator[ListingItem, None]:
        """Stateful WebForms search: GET page 1, then POST __doPostBack to
        walk pages 2..N — each POST needs the freshly returned VIEWSTATE.
        After that we hand off to the standard parallel detail-fetch
        pipeline.
        """
        self.progress.set_phase("search")
        self.progress.set_description(f"{self.portal_name} cerca pag 1")

        first_html = await self.fetch(self.search_url)
        if not first_html:
            self.progress.set_phase("failed")
            return

        soup = BeautifulSoup(first_html, "lxml")
        viewstate = _hidden_field(soup, "__VIEWSTATE")
        viewstate_gen = _hidden_field(soup, "__VIEWSTATEGENERATOR")

        total_pages = await self.get_total_pages(first_html)
        total_pages = min(total_pages, params.max_pages)

        all_urls: list[str] = list(await self.parse_search_results(first_html))
        self.progress.set_description(
            f"{self.portal_name} cerca pag 1/{total_pages} ({len(all_urls)} url)"
        )

        # Abort pagination after this many consecutive POST failures —
        # usually means the WebForms session is dead (WAF, cookie rotation,
        # viewstate rejected). Better to stop early than hammer the server.
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3

        for page in range(2, total_pages + 1):
            page_html = await self._post_search(page, viewstate, viewstate_gen)
            if not page_html:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue
            consecutive_failures = 0
            # Refresh viewstate for the next postback — ASP.NET regenerates
            # it per response.
            page_soup = BeautifulSoup(page_html, "lxml")
            viewstate = _hidden_field(page_soup, "__VIEWSTATE") or viewstate
            viewstate_gen = _hidden_field(page_soup, "__VIEWSTATEGENERATOR") or viewstate_gen

            page_urls = await self.parse_search_results(page_html)
            all_urls.extend(page_urls)
            self.progress.set_description(
                f"{self.portal_name} cerca pag {page}/{total_pages} ({len(all_urls)} url)"
            )

        # Dedupe (page 1 always carries 99 sidebar/featured IDs that recur).
        seen: set[str] = set()
        listing_urls: list[str] = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                listing_urls.append(u)

        if not listing_urls:
            self.progress.set_phase("done")
            return

        # Fresh-skip handling — same shape as BaseSpider.run().
        fresh_ids = params.fresh_source_ids or set()
        to_fetch: list[str] = []
        for url in listing_urls:
            sid = self._extract_source_id_from_url(url)
            if sid and sid in fresh_ids:
                self.fresh_skipped_ids.append(sid)
            else:
                to_fetch.append(url)

        if not to_fetch:
            self.progress.set_phase("done")
            return

        self.progress.set_phase("fetch")
        self.progress.set_total(len(to_fetch))
        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_and_parse(url: str) -> ListingItem | None:
            async with sem:
                html = await self.fetch(url)
                if not html:
                    self.progress.advance()
                    return None
                try:
                    item = await self.parse_listing(url, html)
                except Exception:
                    item = None
                self.progress.advance()
                return item

        tasks = [asyncio.create_task(fetch_and_parse(u)) for u in to_fetch]
        for coro in asyncio.as_completed(tasks):
            item = await coro
            if item:
                yield item

        self.progress.set_phase("done")

    async def parse_listing(self, url: str, html: str) -> ListingItem | None:
        source_id = self._extract_source_id_from_url(url)
        if not source_id:
            return None

        soup = BeautifulSoup(html, "lxml")

        # H1 carries city + zone + property phrase
        h1 = soup.find("h1")
        h1_text = h1.get_text(" ", strip=True) if h1 else ""
        city, zone, type_phrase = _split_h1(h1_text)
        city = (city or "").lower() or "unknown"

        # OG meta tags — title/description are reliable
        def _og(name: str) -> str | None:
            el = soup.find("meta", {"property": name})
            return el.get("content") if el else None

        og_title = _og("og:title") or h1_text
        og_desc = _og("og:description")
        og_image = _og("og:image")

        title = og_title or h1_text or f"Annuncio vistocasa {source_id}"
        description = og_desc

        # Build a label→value map from the inline detail stream
        text_stream = _strip_tags(html)
        labels = _build_label_map(text_stream)

        price = _parse_price(_label_lookup(labels, "PREZZO"))
        # SUPERFICIE typically reads "50 m 2" (the "2" is the m² superscript
        # text). _parse_area picks up the leading number and ignores the rest.
        area_sqm = _parse_area(_label_lookup(labels, "SUPERFICIE"))
        rooms = _parse_int(_label_lookup(labels, "LOCALI", "VANI"))
        bathrooms = _parse_int(_label_lookup(labels, "BAGNI", "SERVIZI"))
        floor_raw = _label_lookup(labels, "PIANO")
        floor = floor_raw.strip() if floor_raw else None
        condition = _label_lookup(labels, "STATO")
        heating = _label_lookup(labels, "RISCALDAMENTO")
        condo_fees = _parse_price(_label_lookup(labels, "SPESE CONDOMINIALI"))
        year_raw = _label_lookup(labels, "ANNO COSTRUZIONE", "ANNO DI COSTRUZIONE")
        year_built = _parse_int(year_raw)

        type_label = _label_lookup(labels, "TIPOLOGIA") or type_phrase or ""
        property_type = map_property_type(type_label)

        ascensore = _label_lookup(labels, "ASCENSORE")
        has_elevator = None
        if ascensore:
            a = ascensore.strip().lower()
            if a.startswith("si") or a.startswith("sì"):
                has_elevator = True
            elif a.startswith("no"):
                has_elevator = False

        # Listing type. CONTRATTO label says "Vendita" / "Affitto" directly;
        # fall back to keyword sniff over the title block when missing.
        contratto = _label_lookup(labels, "CONTRATTO")
        listing_type = _detect_listing_type(contratto, h1_text, og_title, type_phrase, title)

        # Energy class — extracted from CLASSE/CERTIFICAZIONE ENERGETICA value
        # ("G", "A4", "B+", ...). The label captures the rest of the row,
        # which on this site is just the class letter.
        energy_class: str | None = None
        energy_raw = _label_lookup(labels, "CERTIFICAZIONE ENERGETICA", "CLASSE ENERGETICA")
        if energy_raw:
            m = re.match(r"\s*([A-G]\d?\+?)", energy_raw.upper())
            if m:
                energy_class = m.group(1)

        # Address/zone: vistocasa rarely prints a street address, but the
        # description often opens with "in via X". Grab it as a best-effort.
        address: str | None = None
        if description:
            m = re.search(r"in\s+via\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ'\s]{2,40})", description)
            if m:
                address = "via " + m.group(1).strip()

        # Images
        images = _extract_images(html, self.base_url, source_id)
        # Fall back to the OG image if our regex missed (rare).
        if not images and og_image:
            img = og_image if og_image.startswith("http") else urljoin(self.base_url, og_image)
            images = [img]

        # Publication date isn't reliably surfaced. Vistocasa shows
        # "Inserito il 12/03/2026" in some templates — try to pick that up.
        publication_date: str | None = None
        m = re.search(
            r"(?:inserito|pubblicato)\s+il\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
            text_stream,
            re.IGNORECASE,
        )
        if m:
            publication_date = parse_italian_date(m.group(1))

        return ListingItem(
            source_portal=self.portal_name,
            source_id=source_id,
            source_url=url,
            title=title,
            description=description,
            price=price,
            area_sqm=area_sqm,
            rooms=rooms,
            bathrooms=bathrooms,
            floor=floor,
            address=address,
            city=city,
            zone=zone,
            province=None,
            lat=None,
            lng=None,
            property_type=property_type,
            listing_type=listing_type,
            images=images,
            energy_class=energy_class,
            condition=condition,
            heating=heating,
            has_elevator=has_elevator,
            condominium_fees=condo_fees,
            year_built=year_built,
            publication_date=publication_date,
        )
