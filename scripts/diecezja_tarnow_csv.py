#!/usr/bin/env python3
"""Scrape archiwum.diecezjatarnow.pl parish-register catalogues into CSV.

Sources:
  - https://archiwum.diecezjatarnow.pl/zasob-1.html (Tarnowska)
  - https://archiwum.diecezjatarnow.pl/zasob-nr-2.html (Sandomierska)
  - https://archiwum.diecezjatarnow.pl/kopie-ksiag-metrykalnych-diecezja-sandomierska.html
    (Rzeszowska)

These pages don't distinguish a "miejscowość" from the "parafia", so
both columns get the same value. Per-type entries are collapsed to one
row per parish with overall min/max year across every date range found.

Usage:
    uv run python scripts/diecezja_tarnow_csv.py                     # stdout, all sources
    uv run python scripts/diecezja_tarnow_csv.py --source tarnow -o tarnow.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    CsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
)

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


def parse_tarnow(soup: BeautifulSoup) -> dict[str, ParishAcc]:
    """zasob-1.html: one <table> per parish; first row is the parish name."""
    out: dict[str, ParishAcc] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        first = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])]
        nonempty = [c for c in first if c]
        if len(nonempty) != 1:
            continue
        parish = nonempty[0].strip()
        if not parish or any(
            h in parish.lower() for h in ("nr tomu", "parafia", "sygnatura", "zakres")
        ):
            continue
        hdr = " ".join(c.get_text(" ", strip=True).lower() for c in rows[1].find_all(["td", "th"]))
        if "nazwa" not in hdr and "zakres" not in hdr:
            continue
        acc = out.setdefault(parish, ParishAcc(parafia=parish))
        for tr in rows[2:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 4:
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
            kinds = detect_types(lata)
            ys = years_in(lata)
            if not kinds:
                continue
            acc = out.setdefault(parish, ParishAcc(parafia=parish))
            for k in kinds:
                acc.add(k, ys)
    return out


def emit(parishes: dict[str, ParishAcc], sink: CsvSink) -> int:
    n = 0
    type_order = ["Chrzty", "Śluby", "Zgony"]
    for parish in sorted(parishes, key=lambda s: s.upper()):
        acc = parishes[parish]
        for kind in type_order:
            ys = acc.years.get(kind)
            if not ys:
                continue
            sink.write_row(
                {
                    "Miejscowość": parish,
                    "Parafia": parish,
                    "Rodzaj Księgi": kind,
                    "Rok od": min(ys),
                    "Rok do": max(ys),
                }
            )
            n += 1
    return n


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_common_args(p, default_delay=0.5)
    p.add_argument(
        "--source",
        choices=[*SOURCES.keys(), "all"],
        default="all",
        help="Which source page to scrape (default: all three).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.input_html is not None:
        # Offline parse of a single fixture. `--source` picks the parser
        # ("tarnow" → multi-table-per-parish, anything else → simple
        # parish/lata table). `all` falls back to the tarnow parser.
        soup = BeautifulSoup(args.input_html.read_text(encoding="utf-8"), "html.parser")
        parser_name = args.source if args.source != "all" else "tarnow"
        parishes = parse_tarnow(soup) if parser_name == "tarnow" else parse_simple_table(soup)
        with CsvSink(args.output, BASE_FIELDS) as sink:
            n = emit(parishes, sink)
        eprint(f"{parser_name} (offline): {len(parishes)} parishes, {n} rows")
        return 0

    targets = list(SOURCES) if args.source == "all" else [args.source]
    session = make_session(args.user_agent)

    total = 0
    with CsvSink(args.output, BASE_FIELDS) as sink:
        for i, name in enumerate(targets):
            if i > 0 and args.delay > 0:
                time.sleep(args.delay)
            url = SOURCES[name]
            html = fetch_text(session, url, timeout=args.timeout, verbose=args.verbose)
            soup = BeautifulSoup(html, "html.parser")
            if name == "tarnow":
                parishes = parse_tarnow(soup)
            else:
                parishes = parse_simple_table(soup)
            n = emit(parishes, sink)
            eprint(f"{name}: {len(parishes)} parishes, {n} rows")
            total += n

    eprint(f"total rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
