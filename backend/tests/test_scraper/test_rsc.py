"""Next.js App Router flight-payload helpers."""

import json

from scraper.utils.rsc import flight_payload, json_values_after, resolve_text


def test_flight_payload_joins_and_unescapes_chunks():
    html = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>"
        for part in ('0:{"a":"cit', 'tà \\"x\\""}\n')
    )
    assert flight_payload(html) == '0:{"a":"città \\"x\\""}\n'


def test_json_values_after_skips_scalars_and_brackets_inside_strings():
    text = '{"p":"$L1"} {"p":{"t":"a ] } [ b","n":[1,{"k":2}]}} {"p":[3]}'
    assert list(json_values_after(text, "p")) == [{"t": "a ] } [ b", "n": [1, {"k": 2}]}, [3]]


def test_json_values_after_survives_truncated_payload():
    assert list(json_values_after('{"p":{"open":', "p")) == []


def test_resolve_text_reference_and_literals():
    body = "è un testo"
    flight = f'0:["$"]\n2a:T{len(body.encode()):x},{body}2b:["next"]'
    assert resolve_text(flight, "$2a") == body
    assert resolve_text(flight, "plain text") == "plain text"
    assert resolve_text(flight, "$undefined") is None
    assert resolve_text(flight, "$ff") is None  # dangling reference
    assert resolve_text(flight, None) is None
