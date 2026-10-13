"""HTML detail-page extraction helpers shared by all spiders.

Real-estate listing pages across Italian portals follow a handful of common
patterns: a description block, a label/value grid of "caratteristiche"
(superficie, piano, locali, bagni, anno di costruzione, spese, riscaldamento,
stato, classe energetica...), image galleries, and a publication date somewhere
in the footer or metadata. These helpers pull that information out regardless
of how the site formats it.
"""

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

ITALIAN_MONTHS = {
    "gennaio": 1, "gen": 1,
    "febbraio": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4,
    "maggio": 5, "mag": 5,
    "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7,
    "agosto": 8, "ago": 8,
    "settembre": 9, "set": 9, "sett": 9,
    "ottobre": 10, "ott": 10,
    "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}

_KEY_RE = re.compile(r"[^a-z0-9]+")


def _norm_key(text: str) -> str:
    return _KEY_RE.sub(" ", text.lower()).strip()


def parse_features(soup: BeautifulSoup) -> dict[str, str]:
    """Extract label->value feature pairs from common HTML patterns.

    Walks definition lists, tables, and list items. Returns a dict keyed by
    normalized label ("classe energetica", "anno di costruzione", ...). First
    match wins so higher-quality structures beat generic "Label: Value" text.
    """
    features: dict[str, str] = {}

    # <dl><dt>Label</dt><dd>Value</dd></dl>
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = _norm_key(dt.get_text(" ", strip=True))
            value = dd.get_text(" ", strip=True)
            if label and value:
                features.setdefault(label, value)

    # <tr><th>Label</th><td>Value</td></tr>
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            label = _norm_key(th.get_text(" ", strip=True))
            value = td.get_text(" ", strip=True)
            if label and value:
                features.setdefault(label, value)

    # Two-cell rows without th
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            label = _norm_key(tds[0].get_text(" ", strip=True))
            value = tds[1].get_text(" ", strip=True)
            if label and value and len(label) < 40:
                features.setdefault(label, value)

    # List items: "<li><span>Label</span><span>Value</span></li>" or "Label: Value"
    for li in soup.select("li"):
        inner = li.find_all(["span", "div", "strong", "b", "p"], recursive=False)
        if len(inner) >= 2:
            label = _norm_key(inner[0].get_text(" ", strip=True))
            value = inner[1].get_text(" ", strip=True)
            if label and value and label != _norm_key(value):
                features.setdefault(label, value)
                continue
        text = li.get_text(" ", strip=True)
        if ":" in text and len(text) < 200:
            label_part, value_part = text.split(":", 1)
            label = _norm_key(label_part)
            value = value_part.strip()
            if label and value and len(label) < 40:
                features.setdefault(label, value)

    # Paragraph-style "Label: Value" inside feature sections
    for el in soup.select("[class*='feature'] p, [class*='detail'] p, [class*='info'] p"):
        text = el.get_text(" ", strip=True)
        if ":" in text and len(text) < 200:
            label_part, value_part = text.split(":", 1)
            label = _norm_key(label_part)
            value = value_part.strip()
            if label and value and len(label) < 40:
                features.setdefault(label, value)

    return features


def lookup(features: dict[str, str], *keywords: str) -> str | None:
    """Return the first value whose label contains any of the given keywords."""
    for key, val in features.items():
        if any(kw in key for kw in keywords):
            return val
    return None


def parse_italian_date(text: str | None) -> str | None:
    """Parse Italian date formats into ISO 8601 date.

    Supports: "12 aprile 2026", "12 apr 2026", "12/04/2026", "12-04-2026",
    "2026-04-12", "12.04.2026".
    """
    if not text:
        return None
    s = text.strip().lower()

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
    if m:
        try:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3))
            if year < 100:
                year += 2000
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})\s+([a-zà-ÿ]+)\s+(\d{4})", s)
    if m:
        month = ITALIAN_MONTHS.get(m.group(2))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1))).date().isoformat()
            except ValueError:
                pass

    return None


_REL_DATE_RE = re.compile(
    r"(?:(un[ao']?|\d+)\s+)"  # "un", "una", "uno" or a number
    r"(minut|or[ae]|giorn|settiman|mes|ann)"
    r"[a-zà-ÿ']*\s+fa",
    re.IGNORECASE,
)

_REL_UNIT_TO_DELTA = {
    "minut": timedelta(minutes=1),
    "or": timedelta(hours=1),
    "giorn": timedelta(days=1),
    "settiman": timedelta(weeks=1),
    "mes": timedelta(days=30),
    "ann": timedelta(days=365),
}


def _parse_relative_italian(text: str) -> str | None:
    """Parse "3 settimane fa" / "un mese fa" into an ISO datetime (UTC)."""
    m = _REL_DATE_RE.search(text.lower())
    if not m:
        return None
    count_raw = m.group(1)
    unit = m.group(2)
    count = 1 if count_raw.startswith("un") else int(count_raw)
    delta = _REL_UNIT_TO_DELTA.get(unit)
    if not delta:
        return None
    return (datetime.now(timezone.utc) - delta * count).isoformat()


# Keywords that typically precede the publication date in Italian real-estate
# pages. Order matters: absolute-date matches win before we fall back to
# relative phrases.
_PUB_DATE_PATTERNS = [
    # "pubblicato il 12/04/2026" / "inserito il 12-04-26"
    re.compile(
        r"(?:pubblicat[oa]|inserit[oa]|online\s+dal|caricat[oa])"
        r"(?:\s+il)?\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        re.IGNORECASE,
    ),
    # "pubblicato il 12 aprile 2026"
    re.compile(
        r"(?:pubblicat[oa]|inserit[oa]|online\s+dal|caricat[oa])"
        r"(?:\s+il)?\s+(\d{1,2}\s+[a-zà-ÿ]+\s+\d{4})",
        re.IGNORECASE,
    ),
    # "aggiornato il 12/04/2026" — stale fallback, still better than nothing
    re.compile(
        r"(?:aggiornat[oa]|ultimo\s+aggiornamento|modificat[oa])"
        r"(?:\s+il)?\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:aggiornat[oa]|ultimo\s+aggiornamento|modificat[oa])"
        r"(?:\s+il)?\s+(\d{1,2}\s+[a-zà-ÿ]+\s+\d{4})",
        re.IGNORECASE,
    ),
    # "Riferimento 12345 - 12/04/2026" (common footer line)
    re.compile(
        r"(?:riferimento|\brif\b\.?|data\s+annuncio).{0,60}?(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:riferimento|\brif\b\.?|data\s+annuncio).{0,60}?(\d{1,2}\s+[a-zà-ÿ]+\s+\d{4})",
        re.IGNORECASE,
    ),
]


def extract_publication_date_from_text(text: str) -> str | None:
    """Scan free-form page text for a publication/update date.

    Tries absolute-date phrases first (pubblicato/inserito/aggiornato/riferimento),
    then falls back to relative Italian phrases like "3 settimane fa" which
    immobiliare.it tends to use on detail pages.
    """
    if not text:
        return None
    for pattern in _PUB_DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            iso = parse_italian_date(m.group(1))
            if iso:
                return iso
    return _parse_relative_italian(text)


# "senza ascensore", "privo di giardino", "non dotato di box auto", "no garage"
_NEGATION_BEFORE = re.compile(
    r"(?:\bsenza|\bpriv[oa] di|\bsprovvist[oa] di|\bassenza di|\bnon (?:c'è|c'e|ha|è dotat[oa] di|e' dotat[oa] di|dotat[oa] di)|\bno)"
    r"(?:\s+\w+){0,2}\s*$"
)


def detect_feature(text: str | None, *keywords: str) -> bool | None:
    """Tri-state feature detection over *listing* text (description,
    feature labels) — never the whole page, whose sidebars, search facets
    and SEO links mention "giardino"/"ascensore" on every listing.

    True if a keyword appears, False if its first mention is negated
    ("senza ascensore"), None if never mentioned (unknown, not "no").
    """
    if not text:
        return None
    t = text.lower()
    hits = [m for kw in keywords for m in re.finditer(re.escape(kw.lower()), t)]
    if not hits:
        return None
    first = min(hits, key=lambda m: m.start())
    window = t[max(0, first.start() - 40): first.start()]
    return not _NEGATION_BEFORE.search(window)


# In a title, the bare word is enough ("IMMOBILE IN ASTA", "Asta appartamento
# a Bari"). Descriptions mention many things, so only phrases that describe
# the sale itself count. Measured on the catalogue (2026-10-13): 381 hits,
# no false positives in the samples.
_AUCTION_TITLE = re.compile(r"\bast[ae]\b", re.IGNORECASE)
_AUCTION_TEXT = re.compile(
    r"\b(?:all['’`]\s?asta|in asta"
    r"|ast[ae] (?:giudiziari[ae]|telematic(?:a|he)|immobiliar[ei]|fallimentar[ei]|pubblic(?:a|he)|on ?line)"
    r"|vendit[ae] (?:giudiziari[ae]|senza incanto|all['’`]incanto|competitiva)"
    r"|base d['’`]\s?asta|procedura esecutiva|esecuzion[ei] immobiliar[ei]|offerta minima|asta del \d)",
    re.IGNORECASE,
)


def detect_auction(title: str | None, description: str | None) -> bool:
    """Whether a listing is a (judicial) auction rather than a normal sale."""
    return bool(
        (title and _AUCTION_TITLE.search(title))
        or (description and _AUCTION_TEXT.search(description))
    )


def yes_no(value) -> bool | None:
    """Map a structured feature value ("sì", "No", 1, True, "presente") to
    a bool; None for anything unrecognisable."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    v = str(value).strip().lower()
    if v.startswith(("sì", "si", "yes", "presente", "true")) or v.isdigit() and int(v) > 0:
        return True
    if v.startswith(("no", "assente", "false")) or v == "0":
        return False
    return None


def clamp_italy_coords(lat, lng):
    """Drop lat/lng pairs that fall outside Italy's bounding box or look
    obviously swapped. Returns ``(lat, lng)`` — either the input unchanged,
    the pair swapped (if swapping puts them in bounds), or ``(None, None)``.

    Italy's mainland + islands fit roughly within (35.4..47.1 N, 6.6..18.6 E).
    We're generous with the box so Sicily/Pantelleria stay in. A common
    bug in agency APIs is flipping the fields — if swapping recovers a
    valid location we take it; otherwise both are dropped.
    """
    try:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        return None, None
    if lat_f is None or lng_f is None:
        return lat_f, lng_f
    # Accept
    if 35.0 <= lat_f <= 48.0 and 6.0 <= lng_f <= 19.0:
        return lat_f, lng_f
    # Try swap — "lng as lat" shows up in a few agency JSON-LD payloads.
    if 35.0 <= lng_f <= 48.0 and 6.0 <= lat_f <= 19.0:
        return lng_f, lat_f
    return None, None


def clamp_publication_date(iso: str | None) -> str | None:
    """Guard against publication dates in the future (clock skew / timezone
    drift in agency CMSes). Returns the original date if plausible, today's
    date if it's within a 2-day fudge, or None if it's clearly absurd.
    """
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None
    today = datetime.now(timezone.utc).date()
    # Tolerate up to 2 days into the future (timezones/clock drift).
    if d <= today:
        return d.isoformat()
    if (d - today).days <= 2:
        return today.isoformat()
    return None


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", str(text))
    return int(m.group()) if m else None


def parse_float_text(text: str | None) -> float | None:
    if text is None:
        return None
    m = re.search(r"[\d.]+,\d+|[\d.]+", str(text))
    if not m:
        return None
    cleaned = m.group().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def map_condition(raw: str | None) -> str | None:
    if not raw:
        return None
    lower = raw.lower()
    if "nuovo" in lower or "costruzione" in lower or "in costruzione" in lower:
        return "nuovo"
    if "ristrutturato" in lower or "ottimo" in lower:
        return "ristrutturato"
    if "da ristrutturare" in lower or "da_ristrutturare" in lower:
        return "da_ristrutturare"
    if "buono" in lower or "abitabile" in lower or "discreto" in lower:
        return "buono"
    return lower.strip() or None


def map_property_type(raw: str | None) -> str:
    if not raw:
        return "apartment"
    lower = raw.lower()
    if "villetta" in lower or "casa indipendente" in lower or "casale" in lower or "rustico" in lower or "palazzo" in lower:
        return "house"
    if "villa" in lower:
        return "villa"
    if "loft" in lower:
        return "loft"
    if "monolocale" in lower:
        return "studio"
    if "terreno" in lower or "edificabile" in lower or "agricol" in lower:
        return "land"
    if "ufficio" in lower or "commerciale" in lower or "negozio" in lower or "magazzino" in lower:
        return "commercial"
    if "attico" in lower or "mansarda" in lower or "appartamento" in lower or "bilocale" in lower or "trilocale" in lower or "quadrilocale" in lower:
        return "apartment"
    return "apartment"
