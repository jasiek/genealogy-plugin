#!/usr/bin/env python3
"""Scrape basia.famula.pl content-all listing into a parish/book-range CSV.

The page at ``https://basia.famula.pl/content-all.php?lang=pl`` inlines the
entire catalogue of indexed localities in one HTML document. Entries are
separated by ``<img src="/images/rule.jpg">`` and follow this shape::

    <b>Locality (pow. county)</b>            (sometimes wrapped in <u>)
    <b>Parafia katolicka</b>                 (or "Urząd Stanu Cywilnego", etc.)
    chrzty: 1818-1874
    małżeństwa: 1818-1820, 1822-1823, ...
    zgony:                                   (empty -> skip)
    inne: 1818-1819

Polish basia labels are normalised to the project's "Rodzaj Księgi" labels:

  - ``urodzenia`` / ``chrzty``     -> ``Chrzty``
  - ``małżeństwa``                 -> ``Śluby``
  - ``zgony``                      -> ``Zgony``
  - ``inne``                       -> ``Inne``

Comma-separated year lists emit one row per span; single-year entries get
``Rok od == Rok do``.

Output columns:
    Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, powiat, source_type

Usage:
    uv run python scripts/basia_csv.py                    # stdout
    uv run python scripts/basia_csv.py -o sources/basia.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    CsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
    parse_year_ranges,
)

URL = "https://basia.famula.pl/content-all.php?lang=pl"
EXTRA_FIELDS = ["powiat", "source_type"]
FIELDNAMES = BASE_FIELDS + EXTRA_FIELDS

BOOK_TYPE_MAP = {
    "urodzenia": "Chrzty",
    "chrzty": "Chrzty",
    "małżeństwa": "Śluby",
    "śluby": "Śluby",
    "zgony": "Zgony",
    "inne": "Inne",
}

_LOCALITY_RE = re.compile(r"^(?P<name>.+?)\s*\(\s*pow\.\s*(?P<powiat>[^)]+?)\s*\)\s*$")


@dataclass(frozen=True)
class BookRow:
    miejscowosc: str
    parafia: str
    rodzaj_ksiegi: str
    rok_od: int
    rok_do: int
    powiat: str
    source_type: str

    def as_csv_row(self) -> dict[str, object]:
        return {
            "Miejscowość": self.miejscowosc,
            "Parafia": self.parafia,
            "Rodzaj Księgi": self.rodzaj_ksiegi,
            "Rok od": self.rok_od,
            "Rok do": self.rok_do,
            "powiat": self.powiat,
            "source_type": self.source_type,
        }


def split_locality(header: str) -> tuple[str, str]:
    """Split ``"Babimost (pow. zielonogórski)"`` -> ``("Babimost", "zielonogórski")``."""
    match = _LOCALITY_RE.match(header.strip())
    if match is None:
        return header.strip(), ""
    return match.group("name").strip(), match.group("powiat").strip()


def parse_entries(html: str) -> list[BookRow]:
    raw_chunks = re.split(r"<img[^>]+rule\.jpg[^>]*>", html, flags=re.IGNORECASE)
    rows: list[BookRow] = []
    for chunk in raw_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        rows.extend(parse_chunk(chunk))
    return rows


def parse_chunk(chunk_html: str) -> list[BookRow]:
    soup = BeautifulSoup(chunk_html, "html.parser")
    for div in soup.find_all("div", class_="progress-container"):
        div.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")

    bolds = soup.find_all("b")
    if not bolds:
        return []

    locality_header = bolds[0].get_text(strip=True)
    if not locality_header or locality_header.lower().startswith("indeksujący"):
        return []
    miejscowosc, powiat = split_locality(locality_header)

    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cut = len(lines)
    for i, ln in enumerate(lines):
        low = ln.lower()
        if low.startswith("razem wpisów") or low.startswith("indeksujący"):
            cut = i
            break
    lines = lines[:cut]

    source_headers = {b.get_text(strip=True) for b in bolds[1:]}

    rows: list[BookRow] = []
    current_source: str | None = None
    for ln in lines[1:]:
        if ln in source_headers:
            current_source = ln
            continue
        if current_source is None:
            continue
        if ":" not in ln:
            continue
        label, value = ln.split(":", 1)
        label_norm = label.strip().lower()
        book_type = BOOK_TYPE_MAP.get(label_norm)
        if book_type is None:
            continue
        for rok_od, rok_do in parse_year_ranges(value):
            rows.append(
                BookRow(
                    miejscowosc=miejscowosc,
                    parafia=current_source,
                    rodzaj_ksiegi=book_type,
                    rok_od=rok_od,
                    rok_do=rok_do,
                    powiat=powiat,
                    source_type=current_source,
                )
            )
    return rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape basia.famula.pl content-all listing to CSV."
    )
    add_common_args(parser, default_timeout=60.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.input_html is not None:
        html = args.input_html.read_text(encoding="utf-8")
    else:
        session = make_session(args.user_agent)
        html = fetch_text(session, URL, timeout=args.timeout, verbose=args.verbose)
    rows = parse_entries(html)
    with CsvSink(args.output, FIELDNAMES) as sink:
        for row in rows:
            sink.write_row(row.as_csv_row())
    eprint(f"Wrote {len(rows)} rows" + (f" to {args.output}" if args.output else " to stdout"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
