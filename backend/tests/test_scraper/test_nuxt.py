import json
import math

from scraper.utils.nuxt import nuxt_payload, pinia_store, unflatten


def page(values: list) -> str:
    return f'<html><script type="application/json" id="__NUXT_DATA__" data-ssr="true">{json.dumps(values)}</script></html>'


def test_objects_and_arrays_hold_indices():
    values = [{"title": 1, "tags": 2, "rooms": 4}, "Bilocale", [3], "centro", 2]
    assert unflatten(values) == {"title": "Bilocale", "tags": ["centro"], "rooms": 2}


def test_shared_and_circular_references_are_preserved():
    shared = unflatten([{"a": 1, "b": 1}, {"x": 2}, "v"])
    assert shared["a"] is shared["b"]

    loop = unflatten([{"self": 0, "name": 1}, "root"])
    assert loop["self"] is loop


def test_framework_wrappers_are_unwrapped():
    values = [["ShallowReactive", 1], {"pinia": 2}, ["Reactive", 3], {"store": 4}, {"count": 5}, 7]
    assert unflatten(values) == {"pinia": {"store": {"count": 7}}}


def test_tagged_types():
    values = [
        {"when": 1, "set": 2, "map": 5, "bare": 8, "missing": -1, "nan": -3},
        ["Date", "2026-10-13T00:00:00.000Z"],
        ["Set", 3, 4],
        "a",
        "b",
        ["Map", 6, 7],
        "k",
        "v",
        ["null", "x", 3],
    ]
    out = unflatten(values)
    assert out["when"] == "2026-10-13T00:00:00.000Z"
    assert out["set"] == ["a", "b"]
    assert out["map"] == {"k": "v"}
    assert out["bare"] == {"x": "a"}
    assert out["missing"] is None
    assert math.isnan(out["nan"])


def test_payload_from_page_and_pinia_store():
    html = page([{"pinia": 1}, {"listings": 2}, {"count": 3}, 42])
    payload = nuxt_payload(html)
    assert pinia_store(payload, "listings") == {"count": 42}
    assert pinia_store(payload, "other") is None


def test_pages_without_a_usable_payload():
    assert nuxt_payload("<html><body>no payload</body></html>") is None
    assert nuxt_payload('<script id="__NUXT_DATA__">{not json</script>') is None
    assert nuxt_payload('<script id="__NUXT_DATA__">[]</script>') is None
