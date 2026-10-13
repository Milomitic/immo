"""Server-rendered state of Nuxt 3 pages.

Nuxt ships the page's data in ``<script id="__NUXT_DATA__">`` serialised
with `devalue`: one flat JSON array whose objects and arrays hold *indices*
into that same array rather than values (so shared and circular references
survive), e.g.

    [{"title": 1, "tags": 2}, "Bilocale", [3], "centro"]

decodes to ``{"title": "Bilocale", "tags": ["centro"]}``. Arrays starting
with a string are tagged types: ``["Date", "2026-10-13T00:00:00.000Z"]``,
``["Set", i, j]``, or framework wrappers such as ``["ShallowReactive", i]``
(Vue reactivity, irrelevant here: unwrapped to the value).
"""

import json
import re
from typing import Any

_SCRIPT_RE = re.compile(r'<script[^>]*\bid="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Negative "indices" stand for values JSON can't carry. Hole (-2): an
# empty slot of a sparse array.
_SPECIAL = {-1: None, -2: None, -3: float("nan"), -4: float("inf"), -5: float("-inf"), -6: -0.0}


def nuxt_payload(html: str) -> Any:
    """The decoded ``__NUXT_DATA__`` of a page, or None if it has none."""
    m = _SCRIPT_RE.search(html)
    if not m:
        return None
    try:
        values = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(values, list) or not values:
        return None
    return unflatten(values)


def unflatten(values: list) -> Any:
    """Rebuild the value devalue flattened into ``values`` (rooted at 0)."""
    hydrated: dict[int, Any] = {}

    def hydrate(index: int) -> Any:
        if index < 0:
            return _SPECIAL.get(index)
        if index in hydrated:
            return hydrated[index]
        value = values[index]
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                hydrated[index] = _revive(value, hydrate)
                return hydrated[index]
            out: list = []
            hydrated[index] = out  # registered first: a child may point back
            out.extend(hydrate(i) for i in value)
            return out
        if isinstance(value, dict):
            obj: dict = {}
            hydrated[index] = obj
            for key, i in value.items():
                obj[key] = hydrate(i)
            return obj
        hydrated[index] = value
        return value

    return hydrate(0)


def _revive(value: list, hydrate) -> Any:
    tag = value[0]
    if tag == "Date":
        return value[1]  # ISO string; callers parse what they need
    if tag == "Set":
        return [hydrate(i) for i in value[1:]]
    if tag in ("Map", "null"):  # "null": an object without prototype
        pairs = range(1, len(value) - 1, 2)
        if tag == "Map":
            return {_key(hydrate(value[i])): hydrate(value[i + 1]) for i in pairs}
        return {value[i]: hydrate(value[i + 1]) for i in pairs}
    if tag in ("RegExp", "BigInt", "Object"):
        return value[1]
    # Framework revivers (Nuxt: ShallowReactive, Reactive, Ref, ShallowRef,
    # EmptyRef, NuxtError, Island, …) each wrap a single value.
    return hydrate(value[1]) if len(value) > 1 and isinstance(value[1], int) else None


def _key(k: Any) -> Any:
    return k if isinstance(k, (str, int, float, bool, type(None))) else json.dumps(k, default=str)


def pinia_store(payload: Any, name: str) -> dict | None:
    """A Pinia store's state from a decoded payload (``payload.pinia[name]``)."""
    if not isinstance(payload, dict):
        return None
    store = (payload.get("pinia") or {}).get(name)
    return store if isinstance(store, dict) else None
