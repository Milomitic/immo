"""Helpers for Next.js App Router pages (React Server Components).

App Router pages carry no ``__NEXT_DATA__`` blob: server-rendered props
travel as a "flight" stream pushed in JSON-escaped chunks,

    <script>self.__next_f.push([1,"...escaped text..."])</script>

Concatenating the decoded chunks yields newline-separated rows such as
``65:[...]`` (JSON) or ``55:T1a2b,<text>`` (a text blob of 0x1a2b UTF-8
bytes, referenced elsewhere as ``"$55"``). Scrapers don't need a full
flight parser: they locate a known key and bracket-match the JSON value
that follows it.
"""

import json
import re
from collections.abc import Iterator
from typing import Any

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_TEXT_REF_RE = re.compile(r"^\$([0-9a-f]+)$")


def flight_payload(html: str) -> str:
    """Concatenated, unescaped flight stream of an App Router page."""
    parts: list[str] = []
    for raw in _PUSH_RE.findall(html):
        try:
            parts.append(json.loads(f'"{raw}"'))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _value_end(text: str, start: int) -> int:
    """Index just past the JSON object/array opening at ``start``, or -1."""
    depth = 0
    in_str = escaped = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return j + 1
    return -1


def json_values_after(text: str, key: str) -> Iterator[Any]:
    """Yield every JSON object/array that is the value of ``"key":``.

    Scalar values are skipped, so ``"property":"$L54"`` (a lazy reference)
    and ``"property":{...}`` (inline data) can share a key safely.
    """
    marker = f'"{key}":'
    pos = 0
    while (i := text.find(marker, pos)) >= 0:
        start = i + len(marker)
        if start < len(text) and text[start] in "{[":
            end = _value_end(text, start)
            if end > 0:
                try:
                    yield json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
                pos = end
                continue
        pos = start


def resolve_text(flight: str, value: str | None) -> str | None:
    """Resolve a ``"$55"`` reference to the ``55:T<hexlen>,`` text row it
    points at. Plain strings are returned unchanged; other ``$``-prefixed
    references (``$undefined``, ``$L54``, …) resolve to None."""
    if not value:
        return None
    if not value.startswith("$"):
        return value
    m = _TEXT_REF_RE.match(value)
    if not m:
        return None
    row = re.search(rf"(?:^|\n){m.group(1)}:T([0-9a-f]+),", flight)
    if not row:
        return None
    # The length prefix counts UTF-8 bytes, not characters.
    size = int(row.group(1), 16)
    return flight[row.end():].encode("utf-8")[:size].decode("utf-8", errors="ignore")
