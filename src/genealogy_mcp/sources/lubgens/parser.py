"""Parse Lubgens search-result HTML into typed records.

The upstream returns a full HTML page rather than an AJAX fragment, but
the relevant content sits in three sections introduced by
``<h2>Znalezione urodzenia / chrzty</h2>``, ``<h2>Znalezione
małżeństwa</h2>`` and ``<h2>Znalezione zgony</h2>``. Each is followed
by a single result ``<table>``. We walk the markup with regex — it is
machine-generated and stable enough not to warrant a full HTML parser.

Result-table column layout:

* Births / deaths: ``Nazwisko, Imię, Parafia, Akt, Rok, Uwagi``.
* Marriages: ``Nazwisko, Imię, Nazwisko (panieńskie), Imię, Parafia,
  Akt, Rok, Uwagi``.

The ``Uwagi`` cell carries an optional scan link (an ``<a>`` wrapping a
``scan.gif`` image) followed by free-text notes. The notes commonly
include ``O: <father>`` and ``M: <mother>`` shorthand which we extract
when present; for marriages those tokens may be prefixed with ``On-``
(groom) and ``Ona-`` (bride) and we surface the groom's parents only.
"""

from __future__ import annotations

import html
import re

from genealogy_mcp.sources.lubgens.models import (
    LubgensRecord,
    LubgensSearchResult,
    RecordType,
)

_SECTIONS: list[tuple[RecordType, str]] = [
    ("birth", "Znalezione urodzenia"),
    ("marriage", "Znalezione małżeństwa"),
    ("death", "Znalezione zgony"),
]

_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"]", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# "wiecej niz 500" indicates the upstream truncated this category.
_COUNT_RE = re.compile(
    r"<b>(urodzeń|ślubów|zgonów)\s*(wiecej niz\s*)?(\d+)</b>\s*razy",
    re.IGNORECASE,
)
_COUNT_KEY = {"urodzeń": "birth", "ślubów": "marriage", "zgonów": "death"}


def _strip_tags(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _section_table(html_doc: str, header: str) -> str | None:
    """Return the inner HTML of the result <table> following an <h2> header."""
    h2 = re.search(re.escape(header), html_doc)
    if not h2:
        return None
    after = html_doc[h2.end() :]
    table = re.search(r"<table[^>]*>(.*?)</table>", after, re.IGNORECASE | re.DOTALL)
    return table.group(1) if table else None


def _parse_year(raw: str) -> int | None:
    s = raw.strip()
    if not s or s == "0":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _split_uwagi(cell: str) -> tuple[str | None, str]:
    """Pull the scan URL out of the UWAGI cell and return (url, plain_notes)."""
    href = _HREF_RE.search(cell)
    scan_url = href.group(1).strip() if href else None
    if scan_url:
        # The fragment up to and including </a> is the link wrapper —
        # strip it so the surviving text is just the human notes.
        without_link = re.sub(
            r"<a\b[^>]*>.*?</a>", " ", cell, count=1, flags=re.IGNORECASE | re.DOTALL
        )
    else:
        without_link = cell
    return scan_url or None, _strip_tags(without_link)


def _parse_parents(notes: str, *, marriage: bool) -> tuple[str | None, str | None]:
    """Extract father / mother shorthand from the notes cell.

    Births / deaths: ``..., O: <father>, M: <mother>, ...``.
    Marriages: ``On- O: <father>, M: <mother>, ..., Ona- O: ..., M: ...``
    — only the groom's parents are surfaced here; the bride's tokens
    remain accessible via the raw ``notes`` string.
    """
    text = notes
    if marriage:
        # Limit search to the groom's segment when both markers exist.
        m = re.search(r"On-\s*(.*?)(?:,\s*Ona-|$)", text)
        if m:
            text = m.group(1)

    father = mother = None
    m = re.search(r"\bO:\s*([^,]+?)(?=,\s*M:|,\s*Ona-|,\s*[A-ZŁŻŹĆŚŃÓĄĘ]\w*:|$)", text)
    if m:
        father = m.group(1).strip() or None
    m = re.search(r"\bM:\s*([^,]+?)(?=,\s*Ona-|,\s*[A-ZŁŻŹĆŚŃÓĄĘ]\w*:|$)", text)
    if m:
        mother = m.group(1).strip() or None
    return father, mother


def _parse_row(row_html: str, record_type: RecordType) -> LubgensRecord | None:
    cells = _TD_RE.findall(row_html)
    if record_type == "marriage":
        if len(cells) < 8:
            return None
        surname = _strip_tags(cells[0])
        given = _strip_tags(cells[1])
        spouse_surname = _strip_tags(cells[2]) or None
        spouse_given = _strip_tags(cells[3]) or None
        parish = _strip_tags(cells[4]) or None
        act = _strip_tags(cells[5]) or None
        year = _parse_year(_strip_tags(cells[6]))
        scan, notes = _split_uwagi(cells[7])
    else:
        if len(cells) < 6:
            return None
        surname = _strip_tags(cells[0])
        given = _strip_tags(cells[1])
        spouse_surname = spouse_given = None
        parish = _strip_tags(cells[2]) or None
        act = _strip_tags(cells[3]) or None
        year = _parse_year(_strip_tags(cells[4]))
        scan, notes = _split_uwagi(cells[5])

    if not surname and not given and not parish:
        return None  # Empty row.
    if surname.startswith("NAZWISKO") and given.startswith("IMI"):
        return None  # Header row — the upstream uses <td><b> instead of <th>.

    if act in {"0", ""}:
        act = None

    father, mother = _parse_parents(notes or "", marriage=record_type == "marriage")

    return LubgensRecord(
        record_type=record_type,
        surname=surname or None,
        given_name=given or None,
        spouse_surname=spouse_surname,
        spouse_given_name=spouse_given,
        parish=parish,
        act_number=act,
        year=year,
        father_name=father,
        mother_name=mother,
        scan_url=scan,
        notes=notes or None,
    )


def parse_search_response(
    body: str,
    *,
    surname_query: str | None = None,
    given_name_query: str | None = None,
) -> LubgensSearchResult:
    counts: dict[str, int] = {}
    truncated: dict[str, bool] = {}
    for match in _COUNT_RE.finditer(body):
        label, more, num = match.group(1).lower(), match.group(2), match.group(3)
        key = _COUNT_KEY.get(label)
        if not key:
            continue
        counts[key] = int(num)
        truncated[key] = bool(more)

    items: list[LubgensRecord] = []
    for record_type, header in _SECTIONS:
        table_html = _section_table(body, header)
        if not table_html:
            continue
        for row in _TR_RE.findall(table_html):
            rec = _parse_row(row, record_type)
            if rec is not None:
                items.append(rec)

    return LubgensSearchResult(
        surname_query=surname_query,
        given_name_query=given_name_query,
        counts=counts,
        truncated=truncated,
        items=items,
    )
