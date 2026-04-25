import re


# Italian address abbreviations to full form
_ADDRESS_REPLACEMENTS = {
    "v.le": "viale",
    "v.": "via",
    "p.zza": "piazza",
    "p.za": "piazza",
    "c.so": "corso",
    "l.go": "largo",
    "str.": "strada",
    "s.s.": "strada statale",
    "vic.": "vicolo",
    "loc.": "localita",
    "fraz.": "frazione",
    "cont.": "contrada",
    "trav.": "traversa",
}


def normalize_address(address: str | None, city: str = "") -> str:
    if not address:
        return ""
    text = address.lower().strip()
    # Apply abbreviation replacements (longest first to avoid partial matches)
    for abbr, full in sorted(_ADDRESS_REPLACEMENTS.items(), key=lambda x: -len(x[0])):
        text = text.replace(abbr, full)
    # Remove punctuation, extra whitespace
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_city(city: str) -> str:
    return city.lower().strip()


def clean_price(price_str: str) -> float | None:
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.,]", "", price_str)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_area(area_str: str) -> float | None:
    if not area_str:
        return None
    match = re.search(r"[\d.,]+", area_str)
    if match:
        cleaned = match.group().replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
