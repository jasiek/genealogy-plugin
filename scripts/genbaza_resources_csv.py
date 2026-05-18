#!/usr/bin/env python3
"""Scrape genbaza-family resource catalogues into a single CSV.

Output columns: Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, host

Two upstream shapes are handled:

* **Layout A — parish catalogue.** Columns: ``LP, USC/Parafia, link,
  Urodzenia, Śluby, Zgony``. One row per parish, three year-range cells
  per row. Used by ``swietogen``, ``pomerania``, ``warmia``.
* **Layout B — archival catalogue.** Columns: ``LP, Źródło, Link,
  Rodzaj danych, [filler,] Zakres lat, Ilość``. One row per archival
  fond. The fond description is freeform Polish (place + record type +
  notes); we keyword-classify it as birth / marriage / death and skip
  rows that don't map to a parish-style record (resident lists,
  notariats, land registers, etc). Used by ``kurpie`` and
  ``polishgenealogy``.

Usage:
    uv run python scripts/genbaza_resources_csv.py                  # stdout
    uv run python scripts/genbaza_resources_csv.py -o sources/genbaza.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    CsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
)
from genealogy_mcp.sources.genbaza.parser import (
    _TABLE_RE,
    _TD_RE,
    _TH_RE,
    _TR_RE,
    _clean_text,
    parse_resources_response,
)

SOURCES: list[str] = [
    "https://swietogen.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://pomerania.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://warmia.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://kurpie.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://polishgenealogy.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
]

EXTRA_FIELDS = ["host"]
FIELDNAMES = BASE_FIELDS + EXTRA_FIELDS

# Layout A column → Rodzaj Księgi label.
TYPE_LABELS: list[tuple[str, str]] = [
    ("births", "Chrzty"),
    ("marriages", "Śluby"),
    ("deaths", "Zgony"),
]

_RANGE_RE = re.compile(r"(\d{3,4})\s*(?:-|–|—)\s*(\d{3,4})")
_YEAR_RE = re.compile(r"\b(\d{3,4})\b")

# Layout B classifier. Order matters: the exclusion patterns are checked
# first so a "lista mieszkańców urodzonych do 1920 roku" row (resident
# register, not a baptism book) doesn't get classified as Chrzty just
# because it contains "urodz".
_LAYOUT_B_EXCLUDE_RE = re.compile(
    r"lista\s+mieszk|rejestr\s+mieszk|notariat|grundbuch"
    r"|księga\s+gruntowa|akta\s+stanu\s+cywilnego\s+nieindeksowane",
    re.IGNORECASE,
)
_LAYOUT_B_RECORD_TYPES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(urodz|chrzt|chrzc)", re.IGNORECASE), "Chrzty"),
    (re.compile(r"\b(ślub|malzenst|małżeńst)", re.IGNORECASE), "Śluby"),
    (re.compile(r"\b(zgon|zmarł|pogrz)", re.IGNORECASE), "Zgony"),
]

# polishgenealogy formats descriptions as "Lista urodzonych, Place 1820-1900".
# Stripping the leading record-type clause lets layout_b_place fall back
# to its normal dash-splitting on the remainder.
_LAYOUT_B_PREFIX_RE = re.compile(
    r"^(lista|wykaz|spis|spisy|akta|rejestr)\s+\w+(?:\s+\w+)?\s*[,:]\s*",
    re.IGNORECASE,
)
_LAYOUT_B_TRAILING_NOISE_RE = re.compile(
    r"\s+(?:miasto|wieś|par\.?|parafia|pow\.?|powiat|gm\.?|gmina|usc)\b.*$",
    re.IGNORECASE,
)


def parse_year_ranges_chunked(cell: str | None) -> list[tuple[int, int]]:
    """Parse a cell like '1827 - 1830, 1834, 1840 - 1845' into (from, to) pairs.

    The genbaza cells use comma-separated chunks (each chunk is either a
    range or a bare year), so we split-then-parse rather than running a
    single document-order regex.
    """
    if not cell:
        return []
    ranges: list[tuple[int, int]] = []
    for chunk in cell.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _RANGE_RE.search(chunk)
        if m:
            ranges.append((int(m.group(1)), int(m.group(2))))
            continue
        m = _YEAR_RE.search(chunk)
        if m:
            y = int(m.group(1))
            ranges.append((y, y))
    return ranges


def split_parish(label: str) -> tuple[str, str]:
    """Split 'Miejscowość - Parafia' into a (miejscowość, parafia) pair."""
    parts = re.split(r"\s+-\s+", label, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return label.strip(), label.strip()


def detect_layout(body: str) -> str:
    """Return 'A' for parish catalogue, 'B' for archival catalogue.

    Layout A advertises an ``USC/Parafia`` header; Layout B uses
    ``Źródło`` + ``Rodzaj danych``. Anything else returns 'A' so the
    existing parser path handles it (and will yield zero rows if the
    body is empty).
    """
    table_match = _TABLE_RE.search(body)
    if table_match is None:
        return "A"
    headers = [_clean_text(h) for h in _TH_RE.findall(table_match.group(1))]
    lowered = [h.lower() for h in headers]
    if any("rodzaj danych" in h for h in lowered):
        return "B"
    return "A"


def _layout_b_zakres_lat_index(headers: list[str]) -> int | None:
    """Find the ``Zakres lat`` column index in a Layout B header row.

    kurpie has 6 columns (index 4); polishgenealogy has 7 (index 5, with
    a filler before it). Returning None means the table shape changed
    upstream and we should bail noisily.
    """
    for i, h in enumerate(headers):
        if "zakres lat" in h.lower():
            return i
    return None


def classify_layout_b_description(description: str) -> str | None:
    """Map a Layout B ``Rodzaj danych`` description to a Rodzaj Księgi label.

    Returns ``None`` for descriptions that don't look like a parish
    birth/marriage/death register (resident lists, notariats, land
    registers, etc); those rows are skipped.
    """
    if not description:
        return None
    if _LAYOUT_B_EXCLUDE_RE.search(description):
        return None
    for pattern, label in _LAYOUT_B_RECORD_TYPES:
        if pattern.search(description):
            return label
    return None


def layout_b_place(description: str) -> str:
    """Extract a best-effort place name from a Layout B description.

    Handles two upstream conventions:

    * kurpie style: ``"Place - record-type year-range"`` — split on
      the first dash and take the left side.
    * polishgenealogy style: ``"Lista urodzonych, Place year-range"`` —
      strip the leading ``Lista|Wykaz|Spis|Akta|Rejestr`` clause, then
      drop the trailing year range and qualifier tokens (``miasto``,
      ``par.``, ``USC``, ``pow.`` …).
    """
    desc = description.strip()
    if (m := _LAYOUT_B_PREFIX_RE.match(desc)) is not None:
        desc = desc[m.end() :]
    parts = re.split(r"\s*[-–—]\s*", desc, maxsplit=1)
    place = parts[0].strip() if parts else desc
    # Drop any trailing year or year-range glued to the place name.
    place = re.sub(r"\s+\d{3,4}.*$", "", place).strip()
    place = _LAYOUT_B_TRAILING_NOISE_RE.sub("", place).strip()
    return place.strip(",;:- ")


def emit_layout_a(body: str, host: str, sink: CsvSink) -> int:
    parsed = parse_resources_response(body, site=host)
    n = 0
    for resource in parsed.items:
        miejsc, parafia = split_parish(resource.parish)
        for attr, label in TYPE_LABELS:
            for y_from, y_to in parse_year_ranges_chunked(getattr(resource, attr)):
                sink.write_row(
                    {
                        "Miejscowość": miejsc,
                        "Parafia": parafia,
                        "Rodzaj Księgi": label,
                        "Rok od": y_from,
                        "Rok do": y_to,
                        "host": host,
                    }
                )
                n += 1
    return n


def emit_layout_b(body: str, host: str, sink: CsvSink) -> int:
    """Emit one CSV row per (description × year-range) for parish-style rows.

    Bails loudly if the table can't be located or if ``Zakres lat`` is
    missing from the header — both signal an upstream layout change
    that the keyword classifier can't be trusted to handle.
    """
    table_match = _TABLE_RE.search(body)
    if table_match is None:
        raise RuntimeError(f"{host}: Layout B body has no #tbl_res table")
    table_html = table_match.group(1)
    header_match = next(iter(_TR_RE.findall(table_html)), None)
    if header_match is None:
        raise RuntimeError(f"{host}: Layout B table has no rows")
    headers = [_clean_text(h) for h in _TH_RE.findall(header_match)]
    zakres_idx = _layout_b_zakres_lat_index(headers)
    if zakres_idx is None:
        raise RuntimeError(f"{host}: Layout B headers missing 'Zakres lat': {headers!r}")
    # The description ("Rodzaj danych") sits at index 3 in both observed
    # column layouts; sanity-check it so an upstream reshuffle doesn't
    # silently classify the wrong cell.
    if not headers[3].lower().startswith("rodzaj danych"):
        raise RuntimeError(
            f"{host}: Layout B expected 'Rodzaj danych' at index 3, got {headers[3]!r}"
        )

    n = 0
    for tr_html in _TR_RE.findall(table_html):
        cells = _TD_RE.findall(tr_html)
        if len(cells) <= zakres_idx:
            continue
        description = _clean_text(cells[3])
        record_type = classify_layout_b_description(description)
        if record_type is None:
            continue
        place = layout_b_place(description)
        if not place:
            continue
        for y_from, y_to in parse_year_ranges_chunked(_clean_text(cells[zakres_idx])):
            sink.write_row(
                {
                    "Miejscowość": place,
                    "Parafia": place,
                    "Rodzaj Księgi": record_type,
                    "Rok od": y_from,
                    "Rok do": y_to,
                    "host": host,
                }
            )
            n += 1
    return n


def emit_for_host(body: str, host: str, sink: CsvSink) -> int:
    layout = detect_layout(body)
    if layout == "B":
        return emit_layout_b(body, host, sink)
    return emit_layout_a(body, host, sink)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_common_args(p, default_delay=5.0, default_timeout=60.0)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.input_html is not None:
        # Offline: parse the fixture once. The "host" column gets a
        # synthetic value derived from the filename so downstream
        # grep/fzf still works.
        host = args.input_html.stem or "offline"
        body = args.input_html.read_text(encoding="utf-8")
        with CsvSink(args.output, FIELDNAMES) as sink:
            n = emit_for_host(body, host, sink)
        eprint(f"{host} (offline): {n} rows")
        return 0

    session = make_session(args.user_agent)

    total = 0
    with CsvSink(args.output, FIELDNAMES) as sink:
        for i, url in enumerate(SOURCES):
            if i > 0 and args.delay > 0:
                time.sleep(args.delay)
            host = urlparse(url).hostname or "unknown"
            body = fetch_text(session, url, timeout=args.timeout, verbose=args.verbose)
            n = emit_for_host(body, host, sink)
            eprint(f"{host}: {n} rows")
            total += n

    eprint(f"total rows: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
