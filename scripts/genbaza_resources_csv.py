#!/usr/bin/env python3
"""Scrape genbaza-family resource catalogues into per-host CSV files.

Output columns: Miejscowość,Parafia,Rodzaj Księgi,Rok od,Rok do

Sources (Layout A — "USC/Parafia + Urodzenia/Śluby/Zgony" tables):
  - https://swietogen.genbaza.pl
  - https://pomerania.genbaza.pl

The "polishgenealogy" and "kurpie" hosts use a different table shape
(archival sources, not parish registers) that doesn't map onto the
five-column schema, so they are skipped.

Usage:
    uv run python scripts/genbaza_resources_csv.py
    uv run python scripts/genbaza_resources_csv.py --out-dir ./out
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

from polish_genealogy_mcp.sources.genbaza.parser import parse_resources_response

SOURCES: list[str] = [
    "https://swietogen.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://pomerania.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Map of the Layout A column → Rodzaj Księgi label the user wants.
TYPE_LABELS: list[tuple[str, str]] = [
    ("births", "Chrzty"),
    ("marriages", "Śluby"),
    ("deaths", "Zgony"),
]

_RANGE_RE = re.compile(r"(\d{3,4})\s*(?:-|–|—)\s*(\d{3,4})")
_YEAR_RE = re.compile(r"\b(\d{3,4})\b")


def parse_year_ranges(cell: str | None) -> list[tuple[int, int]]:
    """Parse a cell like '1827 - 1830, 1834, 1840 - 1845' into (from, to) pairs."""
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
    """Split 'Miejscowość - Parafia' into a (miejscowość, parafia) pair.

    Falls back to using the same value for both fields when there's no
    explicit separator (single-name parishes).
    """
    parts = re.split(r"\s+-\s+", label, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return label.strip(), label.strip()


def fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    resp.raise_for_status()
    return resp.text


def write_csv(url: str, body: str, out_dir: str) -> tuple[str, int]:
    host = urlparse(url).hostname or "unknown"
    parsed = parse_resources_response(body, site=host)
    path = os.path.join(out_dir, f"{host}.csv")
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Miejscowość", "Parafia", "Rodzaj Księgi", "Rok od", "Rok do"])
        for resource in parsed.items:
            miejsc, parafia = split_parish(resource.parish)
            for attr, label in TYPE_LABELS:
                for y_from, y_to in parse_year_ranges(getattr(resource, attr)):
                    writer.writerow([miejsc, parafia, label, y_from, y_to])
                    rows += 1
    return path, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    default_out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources"
    )
    ap.add_argument(
        "--out-dir",
        default=default_out,
        help=f"Directory for output CSVs (default: {default_out})",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=5.0,
        help="Seconds to wait between source fetches (default: 5)",
    )
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    for i, url in enumerate(SOURCES):
        if i > 0:
            time.sleep(args.sleep)
        print(f"Fetching {url}", file=sys.stderr)
        body = fetch(url)
        path, rows = write_csv(url, body, args.out_dir)
        print(f"  → {path} ({rows} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
