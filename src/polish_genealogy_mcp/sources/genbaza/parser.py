"""Parse genbaza HTML response fragments into typed records.

The upstream serves an HTML snippet (not a full document) per AJAX call.
We avoid pulling in BeautifulSoup; the markup is regular enough to walk
with regex. Two layouts share one parser:

* **Variant A** (10 columns): ``LP, Akt/Strona, Rok, USC/Parafia, Imię,
  Nazwisko, Imię ojca, Imię matki, Nazwisko matki, Inne informacje``.
  Per-record-type counts live in the ``#info`` div or on the menu
  buttons (``Urodzenia (znalez. rekordy: 6156)``).
* **Variant B** (7 columns): ``LP, Nazwisko, Imię, Imię ojca, Imię
  matki, Nazwisko matki, Inne informacje``. The total is on
  ``#info`` as ``Znalezionych rekordów: N``; year is buried in the
  notes cell as ``Rok: NNNN``.
"""

from __future__ import annotations

import html
import re

from polish_genealogy_mcp.sources.genbaza.constants import RODZ_TO_RECORD_TYPE
from polish_genealogy_mcp.sources.genbaza.models import (
    GenbazaRecord,
    GenbazaResource,
    GenbazaResourceList,
    GenbazaSearchResult,
    RecordType,
)

_INFO_RE = re.compile(r"<div\s+id=['\"]info['\"][^>]*>(.*?)</div>", re.IGNORECASE | re.DOTALL)
_MENU_RE = re.compile(r"<div\s+id=['\"]menu['\"][^>]*>(.*?)</div>", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(
    r"<table[^>]*\bid=['\"]tbl_res['\"][^>]*>(.*?)</table>",
    re.IGNORECASE | re.DOTALL,
)
_PAGINATION_RE = re.compile(
    r"<div\s+id=['\"]paginacja1['\"][^>]*>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
# The upstream sometimes omits the closing </tr> and relies on HTML5's
# implicit row close (next <tr> or </table>). The lookahead handles both
# the well-formed and the implicit-close cases. \Z covers the case where
# _TABLE_RE has already stripped </table> and the last row has no </tr>
# (warmia's single-row resource catalogue, for example).
_TR_RE = re.compile(
    r"<tr\b[^>]*>(.*?)(?=<tr\b|</table>|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th>", re.IGNORECASE | re.DOTALL)
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r"href=['\"]([^'\"]+)['\"]", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_VALUE_ATTR_RE = re.compile(r"value=['\"]([^'\"]*)['\"]", re.IGNORECASE)

_COUNT_RE = re.compile(r"(Urodzenia|Śluby|Zgony)\s*\(znalez\.\s*rekordy:\s*(\d+)\)")
_TOTAL_RE = re.compile(r"Znalezionych rekordów:\s*(\d+)")
_PAGES_RE = re.compile(r"\bz\s+(\d+)\b")
_PRIMARY_RE = re.compile(r"Tabela z wynikami dla (urodzeń|ślubów|zgonów)")
_NO_RESULTS = "Nie znaleziono"

_PRIMARY_LABEL_PL: dict[str, RecordType] = {
    "urodzeń": "birth",
    "ślubów": "marriage",
    "zgonów": "death",
}
_COUNT_LABEL_PL: dict[str, RecordType] = {
    "Urodzenia": "birth",
    "Śluby": "marriage",
    "Zgony": "death",
}
_SCAN_DOMAIN = "genbaza.pl"


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s)


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    text = html.unescape(_strip_tags(s))
    return re.sub(r"\s+", " ", text).strip()


def _parse_int(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    # The upstream uses "0" as a sentinel for "year unknown"; treat it as
    # missing rather than the literal year zero.
    if s in ("", "0"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _extract_notes(
    cell_html: str,
) -> tuple[list[str], str | None, str | None, str | None, int | None]:
    """Pull ``(notes, scan_url, archive_ref, indexer, year)`` from the last
    cell of a result row. Works for both layout variants."""
    notes: list[str] = []
    scan_url: str | None = None
    archive_ref: str | None = None
    indexer: str | None = None
    year: int | None = None

    for li_html in _LI_RE.findall(cell_html):
        text = _clean_text(li_html)
        if not text:
            continue
        notes.append(text)

        if scan_url is None:
            for href in _HREF_RE.findall(li_html):
                if _SCAN_DOMAIN in href:
                    scan_url = href
                    break

        low = text.lower()

        # Variant B encodes facts as "Key: value" inside the notes cell.
        if ":" in text:
            key, _, value = text.partition(":")
            key_norm = key.strip().lower()
            value = value.strip()
            if key_norm.startswith("rok") and year is None:
                y = _parse_int(value)
                if y is not None:
                    year = y
            elif key_norm.startswith(("autor indeksu", "indexer")):
                indexer = value
            elif key_norm.startswith(("źródło", "zrodlo", "source")):
                archive_ref = value

        # Variant A drops "autor indeksu: NAME" as freeform text.
        if indexer is None and low.startswith("autor indeksu") and ":" in text:
            indexer = text.split(":", 1)[1].strip() or None

        # Variant A archive shelfmarks start with "AP " (Archiwum
        # Państwowe). Strip a trailing ", SKAN" that gets concatenated
        # when the link text is inlined into the cell.
        if archive_ref is None and re.match(r"^AP\s+\w", text):
            archive_ref = re.sub(r",?\s*SKAN\s*$", "", text).strip().rstrip(",")

    return notes, scan_url, archive_ref, indexer, year


def _detect_variant(table_html: str) -> int:
    """Return 10 for variant A, 7 for variant B (column counts)."""
    headers = _TH_RE.findall(table_html)
    return 10 if len(headers) >= 9 else 7


def _parse_rows(
    table_html: str,
    *,
    site: str,
    record_type_label: RecordType | None,
) -> list[GenbazaRecord]:
    columns = _detect_variant(table_html)
    out: list[GenbazaRecord] = []
    for tr_html in _TR_RE.findall(table_html):
        cells = _TD_RE.findall(tr_html)
        if not cells or len(cells) < columns:
            continue

        if columns == 10:
            (
                _lp,
                act_or_page,
                year_cell,
                parish,
                given,
                surname,
                father,
                mother,
                mother_surname,
                notes_cell,
            ) = cells[:10]
        else:
            (
                _lp,
                surname,
                given,
                father,
                mother,
                mother_surname,
                notes_cell,
            ) = cells[:7]
            act_or_page = year_cell = parish = ""

        notes, scan_url, archive_ref, indexer, year_from_notes = _extract_notes(notes_cell)
        year = _parse_int(_clean_text(year_cell)) or year_from_notes

        out.append(
            GenbazaRecord(
                site=site,
                record_type=record_type_label,
                surname=_clean_text(surname) or None,
                given_name=_clean_text(given) or None,
                father_name=_clean_text(father) or None,
                mother_name=_clean_text(mother) or None,
                mother_surname=_clean_text(mother_surname) or None,
                parish=_clean_text(parish) or None,
                year=year,
                act_or_page=_clean_text(act_or_page) or None,
                notes=notes,
                archive_ref=archive_ref,
                scan_url=scan_url,
                indexer=indexer,
            )
        )
    return out


def parse_search_response(
    body: str,
    *,
    site: str,
    requested_record_type: int,
) -> GenbazaSearchResult:
    info = _clean_text(_INFO_RE.search(body).group(1)) if _INFO_RE.search(body) else ""
    menu_html = _MENU_RE.search(body).group(1) if _MENU_RE.search(body) else ""
    table_match = _TABLE_RE.search(body)
    pagination_match = _PAGINATION_RE.search(body)

    counts: dict[str, int] = {}
    for label, count in _COUNT_RE.findall(info):
        counts[_COUNT_LABEL_PL[label]] = int(count)
    if menu_html:
        # Variant A puts the per-type counts on the menu buttons instead
        # of in #info on the active tab.
        for value in _VALUE_ATTR_RE.findall(menu_html):
            for label, count in _COUNT_RE.findall(value):
                counts[_COUNT_LABEL_PL[label]] = int(count)

    primary_label: RecordType | None = RODZ_TO_RECORD_TYPE.get(requested_record_type)
    if (m := _PRIMARY_RE.search(info)) is not None:
        primary_label = _PRIMARY_LABEL_PL[m.group(1)]

    if (m := _TOTAL_RE.search(info)) is not None and not counts:
        # Variant B: one combined table, no per-type breakdown.
        counts["total"] = int(m.group(1))
        primary_label = None

    total_pages: int | None = None
    if pagination_match is not None:
        if (m := _PAGES_RE.search(_clean_text(pagination_match.group(1)))) is not None:
            total_pages = int(m.group(1))

    items: list[GenbazaRecord] = []
    if table_match is not None and _NO_RESULTS not in info:
        items = _parse_rows(table_match.group(1), site=site, record_type_label=primary_label)

    return GenbazaSearchResult(
        site=site,
        page=1,  # caller overwrites with the page number it asked for
        record_type=primary_label,
        counts=counts,
        total_pages=total_pages,
        items=items,
    )


def parse_resources_response(body: str, *, site: str) -> GenbazaResourceList:
    summary = _clean_text(_INFO_RE.search(body).group(1)) if _INFO_RE.search(body) else None
    table_match = _TABLE_RE.search(body)
    items: list[GenbazaResource] = []
    if table_match is not None:
        for tr_html in _TR_RE.findall(table_match.group(1)):
            cells = _TD_RE.findall(tr_html)
            if len(cells) < 6:
                continue
            parish = _clean_text(cells[1])
            if not parish:
                continue
            items.append(
                GenbazaResource(
                    site=site,
                    parish=parish,
                    births=_clean_text(cells[3]) or None,
                    marriages=_clean_text(cells[4]) or None,
                    deaths=_clean_text(cells[5]) or None,
                )
            )
    return GenbazaResourceList(site=site, summary=summary or None, items=items)


__all__ = [
    "parse_search_response",
    "parse_resources_response",
    "_extract_notes",  # exported for tests
]
