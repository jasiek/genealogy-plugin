#!/usr/bin/env python3
"""Scrape archiwum.diecezjatarnow.pl parish-register catalogues into CSV.

Output columns: Miejscowość,Parafia,Rodzaj Księgi,Rok od,Rok do

Sources:
  - https://archiwum.diecezjatarnow.pl/zasob-1.html
      (Diecezja Tarnowska — one HTML table per parish, parish name is
       the first row of each table, columns: nr tomu / nazwa / zakres
       dat / sygnatura / uwagi. Rows with empty `nr tomu` continue the
       previous volume.)
  - https://archiwum.diecezjatarnow.pl/zasob-nr-2.html
      (Diecezja Sandomierska — single table: Parafia / Lata / Sygnatura)
  - https://archiwum.diecezjatarnow.pl/kopie-ksiag-metrykalnych-diecezja-sandomierska.html
      (Diecezja Rzeszowska — same shape as zasob-nr-2.)

These pages don't distinguish a "miejscowość" from the "parafia", so
both columns get the same value.

Per-type (Chrzty / Śluby / Zgony) entries are collapsed to one row per
parish with the overall min/max year across every date range found.

Usage:
    uv run python scripts/diecezja_tarnow_csv.py > out.csv
    uv run python scripts/diecezja_tarnow_csv.py --source tarnow > tarnow.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable

import requests
from bs4 import BeautifulSoup

SOURCES = {
    "tarnow": "https://archiwum.diecezjatarnow.pl/zasob-1.html",
    "sandomierska": "https://archiwum.diecezjatarnow.pl/zasob-nr-2.html",
    "rzeszowska": "https://archiwum.diecezjatarnow.pl/kopie-ksiag-metrykalnych-diecezja-sandomierska.html",
}

# Map register-type keywords -> output label.
TYPE_PATTERNS = [
    (
        "Chrzty",
        re.compile(r"(natorum|ochrzczen|chrzty|chrzt[oó]w|baptiz|baptis|urodzen|urodzin)", re.I),
    ),
    ("Śluby", re.compile(r"(copulator|małżeństw|malzenstw|ślub|slub|zaślubien|zaslubien)", re.I)),
    ("Zgony", re.compile(r"(mortuorum|zmarł|zmarl|zgon|defunct|pogrzeb)", re.I)),
]

YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


@dataclass
class ParishAcc:
    """Accumulates min/max year per register type for one parish."""

    parafia: str
    years: dict[str, list[int]] = field(default_factory=dict)

    def add(self, kind: str, years: Iterable[int]) -> None:
        ys = [y for y in years if y]
        if not ys:
            return
        bucket = self.years.setdefault(kind, [])
        bucket.extend(ys)


def detect_types(text: str) -> list[str]:
    return [label for label, pat in TYPE_PATTERNS if pat.search(text)]


def years_in(text: str) -> list[int]:
    return [int(m) for m in YEAR_RE.findall(text)]


def fetch(url: str) -> BeautifulSoup:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; diecezja-tarnow-csv/1.0)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def parse_tarnow(soup: BeautifulSoup) -> dict[str, ParishAcc]:
    """zasob-1.html: one <table> per parish; first row contains the
    parish name (single cell), second row is headers, then volume rows.
    """
    out: dict[str, ParishAcc] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        first = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])]
        # Heuristic: parish-name row has exactly one non-empty cell and no header-like words.
        nonempty = [c for c in first if c]
        if len(nonempty) != 1:
            continue
        parish = nonempty[0].strip()
        if not parish or any(
            h in parish.lower() for h in ("nr tomu", "parafia", "sygnatura", "zakres")
        ):
            continue
        # Header row check
        hdr = " ".join(c.get_text(" ", strip=True).lower() for c in rows[1].find_all(["td", "th"]))
        if "nazwa" not in hdr and "zakres" not in hdr:
            continue
        acc = out.setdefault(parish, ParishAcc(parafia=parish))
        for tr in rows[2:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            # Take the "nazwa" + "zakres dat" columns.
            # Layouts seen: 5-col (with nr tomu) or 4-col (continuation rows
            # missing the nr tomu cell).
            if len(cells) >= 5:
                nazwa, zakres = cells[1], cells[2]
            elif len(cells) == 4:
                nazwa, zakres = cells[1], cells[2]
            elif len(cells) == 3:
                nazwa, zakres = cells[0], cells[1]
            elif len(cells) == 2:
                nazwa, zakres = cells[0], cells[1]
            else:
                continue
            kinds = detect_types(nazwa)
            ys = years_in(zakres)
            for k in kinds:
                acc.add(k, ys)
    return out


def parse_simple_table(soup: BeautifulSoup) -> dict[str, ParishAcc]:
    """zasob-nr-2.html / sandomierska: a single Parafia/Lata/Sygnatura table."""
    out: dict[str, ParishAcc] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        # Skip header rows (look for "Parafia" anywhere).
        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            if (
                cells[0].lower() in ("parafia",)
                or "parafia" in cells[0].lower()
                and "lata" in " ".join(cells).lower()
            ):
                continue
            parish = cells[0].strip()
            lata = cells[1] if len(cells) >= 2 else ""
            if not parish or not lata:
                continue
            # The second column is e.g. "Ochrzczeni: 1801 - 1841" — type in
            # the same string as the years.
            kinds = detect_types(lata)
            ys = years_in(lata)
            if not kinds:
                continue
            acc = out.setdefault(parish, ParishAcc(parafia=parish))
            for k in kinds:
                acc.add(k, ys)
    return out


def emit(parishes: dict[str, ParishAcc], writer: csv.writer) -> int:
    n = 0
    # Stable order: alphabetical by parish, then fixed type order.
    type_order = ["Chrzty", "Śluby", "Zgony"]
    for parish in sorted(parishes, key=lambda s: s.upper()):
        acc = parishes[parish]
        for kind in type_order:
            ys = acc.years.get(kind)
            if not ys:
                continue
            writer.writerow([parish, parish, kind, min(ys), max(ys)])
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--source",
        choices=[*SOURCES.keys(), "all"],
        default="all",
        help="Which source page to scrape (default: all three).",
    )
    p.add_argument("-o", "--output", help="Write CSV here instead of stdout.")
    args = p.parse_args(argv)

    targets = list(SOURCES) if args.source == "all" else [args.source]

    out_fh = open(args.output, "w", encoding="utf-8", newline="") if args.output else sys.stdout
    writer = csv.writer(out_fh)
    writer.writerow(["Miejscowość", "Parafia", "Rodzaj Księgi", "Rok od", "Rok do"])

    total = 0
    for name in targets:
        url = SOURCES[name]
        print(f"# fetching {url}", file=sys.stderr)
        soup = fetch(url)
        if name == "tarnow":
            parishes = parse_tarnow(soup)
        else:
            parishes = parse_simple_table(soup)
        n = emit(parishes, writer)
        print(f"# {name}: {len(parishes)} parishes, {n} rows", file=sys.stderr)
        total += n

    print(f"# total rows: {total}", file=sys.stderr)
    if args.output:
        out_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
