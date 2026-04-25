"""Shared schema.org JSON-LD extraction helpers for agency-site spiders."""

import json

from bs4 import BeautifulSoup

_LISTING_TYPES = {
    "product", "residence", "singlefamilyresidence", "apartment",
    "house", "realestatelisting", "offer", "accommodation",
}


def extract_listing_jsonld(soup: BeautifulSoup) -> dict | None:
    """Return the first JSON-LD block whose @type matches a real-estate listing."""
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, ValueError):
            continue
        for block in _iter_blocks(data):
            t = block.get("@type", "")
            types = t if isinstance(t, list) else [t]
            for tp in types:
                if str(tp).lower() in _LISTING_TYPES:
                    return block
    return None


def _iter_blocks(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_blocks(item)
    elif isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_blocks(item)


def parse_price(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("€", "").replace(".", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None
