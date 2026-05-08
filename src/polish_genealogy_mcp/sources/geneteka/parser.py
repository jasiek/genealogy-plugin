"""Parse Geneteka's DataTables JSON rows into typed records.

Geneteka's `api/getAct.php` returns rows as positional arrays whose layout
depends on `bdm`:

  Births (B) and Deaths (D), 10 cols:
    Rok, Akt, Imię, Nazwisko, Imię ojca, Imię matki, Nazwisko matki,
    Parafia, Miejscowość, Uwagi (HTML)

  Marriages (S), 10 cols:
    Rok, Akt, Imię(M), Nazwisko(M), Rodzice(M),
    Imię(F), Nazwisko(F), Rodzice(F), Parafia, Uwagi (HTML)

The Uwagi cell is a small HTML fragment with several anchors and an info
icon whose `title` carries human-readable comments (birth dates, ages,
remarks). We extract: comments, archive name, indexer username, gid (the
stable Geneteka record id used by the corrections endpoint), and a fix URL.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

from polish_genealogy_mcp.sources.geneteka.models import (
    GenetekaPerson,
    GenetekaRecord,
    RecordType,
)

_FIX_GID_RE = re.compile(r"fix\.php\?[^\"']*gid=(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"title=\"([^\"]*)\"", re.IGNORECASE)
_HREF_RE = re.compile(r"href=\"([^\"]*)\"", re.IGNORECASE)
_UNAME_RE = re.compile(r"uname=([^\"&]+)", re.IGNORECASE)


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = html.unescape(s).replace("\r", " ").replace("\n", " ").strip()
    return s or None


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


def _parse_uwagi(raw: str | None) -> dict[str, str | int | None]:
    """Extract structured bits from the Uwagi HTML cell.

    The cell typically contains:
      - <img title="... comments ..."> — free-text remarks (incl. exact dates)
      - <a href="archive-url" ...><img title="archive description"></a>
      - <a href=".../user.php?...uname=USER"><img title="Indeks dodał: USER"></a>
      - <a href="fix.php?gid=NNN&..."><img title="Zgłoś poprawkę"></a>

    We capture the most useful free-text without trying to fully understand
    the HTML — a full parse is not worth the dependency footprint.
    """
    out: dict[str, str | int | None] = {
        "gid": None,
        "comments": None,
        "archive": None,
        "indexer": None,
        "fix_url": None,
    }
    if not raw:
        return out

    if (m := _FIX_GID_RE.search(raw)) is not None:
        try:
            out["gid"] = int(m.group(1))
        except ValueError:
            pass

    titles = [_clean(t) for t in _TITLE_RE.findall(raw)]
    titles = [t for t in titles if t]
    # The first non-link <img> title is the comments tooltip; later titles
    # belong to archive / indexer / fix anchors. We classify by content
    # rather than position so column reordering can't silently mislabel.
    for t in titles:
        low = t.lower()
        if low.startswith("zgłoś") or "popraw" in low:
            continue
        if low.startswith("indeks dodał") or low.startswith("indeks dodała"):
            # "Indeks dodał: <username>"
            after_colon = t.split(":", 1)
            if len(after_colon) == 2:
                out["indexer"] = after_colon[1].strip() or None
            continue
        if "archiwum" in low or "miejsce przechowywania" in low:
            out["archive"] = t
            continue
        # Anything else — most often "Data urodzenia: ..." or free remarks.
        if out["comments"] is None:
            out["comments"] = t
        else:
            out["comments"] = f"{out['comments']} | {t}"

    if out["indexer"] is None:
        for href in _HREF_RE.findall(raw):
            if "uname=" in href:
                if (m := _UNAME_RE.search(href)) is not None:
                    out["indexer"] = _clean(m.group(1))
                    break

    for href in _HREF_RE.findall(raw):
        if "fix.php" in href:
            out["fix_url"] = html.unescape(href)
            break

    return out


def _row_birth_or_death(
    row: list[str],
    record_type: RecordType,
    region_code: str,
) -> GenetekaRecord:
    uwagi = _parse_uwagi(row[9] if len(row) > 9 else None)
    person = GenetekaPerson(
        given_name=_clean(row[2]) if len(row) > 2 else None,
        surname=_clean(row[3]) if len(row) > 3 else None,
        father_given=_clean(row[4]) if len(row) > 4 else None,
        mother_given=_clean(row[5]) if len(row) > 5 else None,
        mother_maiden=_clean(row[6]) if len(row) > 6 else None,
    )
    return GenetekaRecord(
        record_type=record_type,
        gid=uwagi["gid"],  # type: ignore[arg-type]
        year=_parse_year(row[0] if len(row) > 0 else None),
        act_no=_clean(row[1]) if len(row) > 1 else None,
        parish=_clean(row[7]) if len(row) > 7 else None,
        place=_clean(row[8]) if len(row) > 8 else None,
        region_code=region_code,
        person=person,
        spouse=None,
        comments=uwagi["comments"],  # type: ignore[arg-type]
        archive=uwagi["archive"],  # type: ignore[arg-type]
        indexer=uwagi["indexer"],  # type: ignore[arg-type]
        fix_url=uwagi["fix_url"],  # type: ignore[arg-type]
    )


def _row_marriage(row: list[str], region_code: str) -> GenetekaRecord:
    uwagi = _parse_uwagi(row[9] if len(row) > 9 else None)
    groom = GenetekaPerson(
        given_name=_clean(row[2]) if len(row) > 2 else None,
        surname=_clean(row[3]) if len(row) > 3 else None,
        parents=_clean(row[4]) if len(row) > 4 else None,
    )
    bride = GenetekaPerson(
        given_name=_clean(row[5]) if len(row) > 5 else None,
        surname=_clean(row[6]) if len(row) > 6 else None,
        parents=_clean(row[7]) if len(row) > 7 else None,
    )
    return GenetekaRecord(
        record_type="marriage",
        gid=uwagi["gid"],  # type: ignore[arg-type]
        year=_parse_year(row[0] if len(row) > 0 else None),
        act_no=_clean(row[1]) if len(row) > 1 else None,
        parish=_clean(row[8]) if len(row) > 8 else None,
        place=None,
        region_code=region_code,
        person=groom,
        spouse=bride,
        comments=uwagi["comments"],  # type: ignore[arg-type]
        archive=uwagi["archive"],  # type: ignore[arg-type]
        indexer=uwagi["indexer"],  # type: ignore[arg-type]
        fix_url=uwagi["fix_url"],  # type: ignore[arg-type]
    )


def parse_rows(
    rows: Iterable[list[str]],
    record_type: RecordType,
    region_code: str,
) -> list[GenetekaRecord]:
    out: list[GenetekaRecord] = []
    for row in rows:
        if record_type == "marriage":
            out.append(_row_marriage(row, region_code))
        else:
            out.append(_row_birth_or_death(row, record_type, region_code))
    return out


def parse_total(payload: dict) -> int:
    """Geneteka returns recordsFiltered as a string; coerce defensively."""
    raw = payload.get("recordsFiltered") or payload.get("recordsTotal") or 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return 0


__all__ = [
    "parse_rows",
    "parse_total",
    "_parse_uwagi",  # exported for tests
]
