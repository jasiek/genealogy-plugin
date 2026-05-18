#!/usr/bin/env python3
"""Scrape Geneteka per-region pages into a parish/book-range CSV.

Each voivodeship page (``?op=gt&w=<code>``) inlines the full parish
catalogue in ``<select id="sel_rid">``. Every option carries:

  - the visible parish/locality name (option text),
  - three event-specific ``rid`` values (``data-b`` for births,
    ``data-s`` for marriages, ``data-d`` for deaths),
  - ``data-years`` text such as ``(U 1873-1925, M 1873-1933, Z 1873-1933)``.

So a single request per region yields everything; with ~22 regions and
the 5s rate limit this finishes in ~2 minutes.

Output columns:
  Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, voivodeship, parish_id

When ``-o`` is set, the run is resumable: a sidecar ``<output>.progress``
file records which region codes have been written. Re-running appends
only the missing ones. Pass ``--restart`` to rebuild from scratch.

Usage:
    uv run python scripts/geneteka_parish_books.py                       # stdout
    uv run python scripts/geneteka_parish_books.py --region 06mp
    uv run python scripts/geneteka_parish_books.py -o sources/geneteka.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    ResumableCsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
)

BASE_URL = "https://geneteka.genealodzy.pl/index.php"
EXTRA_FIELDS = ["voivodeship", "parish_id"]
FIELDNAMES = BASE_FIELDS + EXTRA_FIELDS

# Geneteka uses U / M / Z in data-years.
EVENT_CATEGORIES: list[tuple[str, str, str]] = [
    # (data-attr, year-prefix in data-years, "Rodzaj Księgi" label)
    ("data-b", "U", "Chrzty"),
    ("data-s", "M", "Śluby"),
    ("data-d", "Z", "Zgony"),
]

_YEAR_RE_TEMPLATE = r"{prefix}\s*(\d{{4}})\s*[-–—]\s*(\d{{4}})"


@dataclass(frozen=True)
class ParishBookRow:
    miejscowosc: str
    parafia: str
    rodzaj_ksiegi: str
    rok_od: int
    rok_do: int
    voivodeship: str
    parish_id: str

    def as_csv_row(self) -> dict[str, object]:
        return {
            "Miejscowość": self.miejscowosc,
            "Parafia": self.parafia,
            "Rodzaj Księgi": self.rodzaj_ksiegi,
            "Rok od": self.rok_od,
            "Rok do": self.rok_do,
            "voivodeship": self.voivodeship,
            "parish_id": self.parish_id,
        }


def fetch_region_page(session, *, region_code: str, timeout: float, verbose: bool) -> str:
    params = {"op": "gt", "lang": "pol", "bdm": "B", "w": region_code}
    url_for_log = f"{BASE_URL}?op=gt&lang=pol&bdm=B&w={region_code}"
    if verbose:
        eprint(f"Fetching {url_for_log}")
    return fetch_text(session, BASE_URL, timeout=timeout, params=params, verbose=False)


def parse_regions(html: str) -> dict[str, str]:
    """Return ``{code: name}`` from the voivodeship dropdown."""
    soup = BeautifulSoup(html, "html.parser")
    select = soup.select_one("select#sel_w")
    if select is None:
        raise ValueError('Could not find <select id="sel_w"> on the page')
    regions: dict[str, str] = {}
    for option in select.find_all("option"):
        code = (option.get("value") or "").strip()
        name = option.get_text(strip=True)
        if code and name:
            regions[code] = name
    if not regions:
        raise ValueError("Voivodeship dropdown was empty")
    return regions


def parse_parishes(
    html: str,
    *,
    region_code: str,
    voivodeship: str,
) -> list[ParishBookRow]:
    soup = BeautifulSoup(html, "html.parser")
    select = soup.select_one("select#sel_rid")
    if select is None:
        raise ValueError(f'Could not find <select id="sel_rid"> for region {region_code}')

    rows: list[ParishBookRow] = []
    for option in select.find_all("option"):
        name = option.get_text(strip=True)
        if not name:
            continue
        years_text = (option.get("data-years") or "").strip()
        if not years_text:
            continue

        for data_attr, prefix, label in EVENT_CATEGORIES:
            rid = (option.get(data_attr) or "").strip()
            if not rid:
                continue
            match = re.search(_YEAR_RE_TEMPLATE.format(prefix=prefix), years_text)
            if match is None:
                continue
            rows.append(
                ParishBookRow(
                    miejscowosc=name,
                    parafia=name,
                    rodzaj_ksiegi=label,
                    rok_od=int(match.group(1)),
                    rok_do=int(match.group(2)),
                    voivodeship=voivodeship,
                    parish_id=rid,
                )
            )
    return rows


def crawl(
    *,
    output: Path | None,
    user_agent: str | None,
    timeout: float,
    delay_seconds: float,
    only_regions: list[str] | None,
    restart: bool,
    verbose: bool,
) -> int:
    session = make_session(user_agent)

    # The first request also gives us the voivodeship dropdown. Use 06mp
    # as the seed since it always exists.
    seed_html = fetch_region_page(session, region_code="06mp", timeout=timeout, verbose=verbose)
    region_names = parse_regions(seed_html)

    if only_regions:
        unknown = [r for r in only_regions if r not in region_names]
        if unknown:
            eprint(f"Warning: unknown region codes ignored: {', '.join(unknown)}")
        codes = [r for r in only_regions if r in region_names]
    else:
        codes = sorted(region_names.keys())

    new_rows = 0
    with ResumableCsvSink(output, FIELDNAMES, restart=restart) as sink:
        for index, code in enumerate(codes, start=1):
            if sink.already_done(code):
                eprint(
                    f"Skipping {index}/{len(codes)}: {code} ({region_names[code]}) — already done"
                )
                continue

            if code == "06mp" and index == 1:
                html = seed_html
            else:
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                html = fetch_region_page(
                    session, region_code=code, timeout=timeout, verbose=verbose
                )

            rows = parse_parishes(html, region_code=code, voivodeship=region_names[code])
            n = sink.write_unit(code, (r.as_csv_row() for r in rows))
            new_rows += n
            eprint(f"Crawled {index}/{len(codes)}: {code} ({region_names[code]}) — {n} rows")

    return new_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Geneteka per-region parish book-range catalogue to CSV."
    )
    add_common_args(parser, default_delay=5.0, supports_resume=True)
    parser.add_argument(
        "--region",
        action="append",
        dest="regions",
        default=None,
        metavar="CODE",
        help=(
            "Limit to one or more region codes (e.g. 06mp). May be repeated. "
            "Defaults to every region in the voivodeship dropdown."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.input_html is not None:
        # Offline: parse a single captured region page. `--region CODE`
        # supplies the voivodeship attribution; absent that, both the
        # code and human name fall back to "offline".
        html = args.input_html.read_text(encoding="utf-8")
        code = args.regions[0] if args.regions else "offline"
        voivodeship = code
        rows = parse_parishes(html, region_code=code, voivodeship=voivodeship)
        with ResumableCsvSink(args.output, FIELDNAMES, restart=args.restart) as sink:
            n = sink.write_unit(code, (r.as_csv_row() for r in rows))
        eprint(
            f"{code} (offline): {n} rows" + (f" → {args.output}" if args.output else " → stdout")
        )
        return 0

    new_rows = crawl(
        output=args.output,
        user_agent=args.user_agent,
        timeout=args.timeout,
        delay_seconds=args.delay,
        only_regions=args.regions,
        restart=args.restart,
        verbose=args.verbose,
    )
    eprint(f"Wrote {new_rows} new rows" + (f" to {args.output}" if args.output else " to stdout"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
