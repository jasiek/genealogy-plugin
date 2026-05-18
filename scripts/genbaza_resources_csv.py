#!/usr/bin/env python3
"""Scrape genbaza-family resource catalogues into a single CSV.

Output columns: Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, host

Sources (Layout A — "USC/Parafia + Urodzenia/Śluby/Zgony" tables):
  - https://swietogen.genbaza.pl
  - https://pomerania.genbaza.pl

The "polishgenealogy" and "kurpie" hosts use a different table shape
(archival sources, not parish registers) and are skipped.

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

from polish_genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    CsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
)
from polish_genealogy_mcp.sources.genbaza.parser import parse_resources_response

SOURCES: list[str] = [
    "https://swietogen.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
    "https://pomerania.genbaza.pl/php/getdata.php?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=&naz_mat=&pag=1&sort1=2&sort2=1&sort3=0&metr=&dokl=000000000000&metod=1&rodz=1&zasob=1",
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


def emit_for_host(body: str, host: str, sink: CsvSink) -> int:
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
