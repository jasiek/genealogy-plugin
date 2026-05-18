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
``Rok od == Rok do``. So ``"1818-1820, 1822-1823, 1825-1829"`` produces
three rows.

Output columns:
    Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, powiat, source_type

``Miejscowość`` is the locality name without the ``(pow. ...)`` suffix; the
county is preserved in ``powiat``. ``Parafia`` mirrors basia's source-block
header (``Parafia katolicka`` / ``Urząd Stanu Cywilnego`` / ...) because the
catalogue does not expose individual parish dedications. ``source_type``
keeps the raw header for downstream filtering.

Usage:
    uv run python scripts/basia_csv.py
    uv run python scripts/basia_csv.py -o sources/basia.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://basia.famula.pl/content-all.php?lang=pl"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
FIELDNAMES = [
    "Miejscowość",
    "Parafia",
    "Rodzaj Księgi",
    "Rok od",
    "Rok do",
    "powiat",
    "source_type",
]

# basia label -> project "Rodzaj Księgi" label.
BOOK_TYPE_MAP = {
    "urodzenia": "Chrzty",
    "chrzty": "Chrzty",
    "małżeństwa": "Śluby",
    "śluby": "Śluby",
    "zgony": "Zgony",
    "inne": "Inne",
}

_LOCALITY_RE = re.compile(r"^(?P<name>.+?)\s*\(\s*pow\.\s*(?P<powiat>[^)]+?)\s*\)\s*$")
_YEAR_RE = re.compile(r"(\d{4})(?:\s*[-–—]\s*(\d{4}))?")


@dataclass(frozen=True)
class BookRow:
    miejscowosc: str
    parafia: str
    rodzaj_ksiegi: str
    rok_od: int
    rok_do: int
    powiat: str
    source_type: str

    def as_csv_row(self) -> dict[str, str | int]:
        return {
            "Miejscowość": self.miejscowosc,
            "Parafia": self.parafia,
            "Rodzaj Księgi": self.rodzaj_ksiegi,
            "Rok od": self.rok_od,
            "Rok do": self.rok_do,
            "powiat": self.powiat,
            "source_type": self.source_type,
        }


def fetch(timeout: float, verbose: bool) -> str:
    if verbose:
        print(f"Fetching {URL}", file=sys.stderr)
    response = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def parse_year_spans(value: str) -> list[tuple[int, int]]:
    """Return every ``(start, end)`` span in ``value`` in document order."""
    spans: list[tuple[int, int]] = []
    for m in _YEAR_RE.finditer(value):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        spans.append((start, end))
    return spans


def split_locality(header: str) -> tuple[str, str]:
    """Split ``"Babimost (pow. zielonogórski)"`` -> ``("Babimost", "zielonogórski")``."""
    match = _LOCALITY_RE.match(header.strip())
    if match is None:
        return header.strip(), ""
    return match.group("name").strip(), match.group("powiat").strip()


def parse_entries(html: str) -> list[BookRow]:
    # Entries are separated by a horizontal-rule image; split the raw HTML
    # on that marker and parse each chunk independently.
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

    # Collect the bold headers in document order: the first is the locality,
    # subsequent ones are source-type headers ("Parafia katolicka",
    # "Urząd Stanu Cywilnego", etc.). Text between source headers contains
    # the "rodzaj: years" lines.
    bolds = soup.find_all("b")
    if not bolds:
        return []

    locality_header = bolds[0].get_text(strip=True)
    if not locality_header or locality_header.lower().startswith("indeksujący"):
        return []
    miejscowosc, powiat = split_locality(locality_header)

    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Drop everything from "Razem wpisów" / "Indeksujący" onward — those are
    # entry-level metadata, not book data.
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
    # Skip the first line (locality header) when iterating.
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
        for rok_od, rok_do in parse_year_spans(value):
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


def write_csv(rows: list[BookRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_row())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape basia.famula.pl content-all listing to CSV."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("sources/basia.csv"),
        help="CSV output path. Defaults to sources/basia.csv.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds. Defaults to 60.",
    )
    parser.add_argument(
        "--input-html",
        type=Path,
        default=None,
        help="Parse a local HTML file instead of fetching (for testing).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print fetch URL to stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.input_html is not None:
        html = args.input_html.read_text(encoding="utf-8")
    else:
        html = fetch(timeout=args.timeout, verbose=args.verbose)
    rows = parse_entries(html)
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
