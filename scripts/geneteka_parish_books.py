#!/usr/bin/env python3
"""Scrape Geneteka per-region pages into a parish/book-range CSV.

Each voivodeship page (``?op=gt&w=<code>``) inlines the full parish catalogue
in ``<select id="sel_rid">``. Every option carries:

  - the visible parish/locality name (option text),
  - three event-specific ``rid`` values (``data-b`` for births, ``data-s`` for
    marriages, ``data-d`` for deaths) — these are the values Geneteka expects
    in the ``rid=`` URL parameter when searching that parish + event type,
  - ``data-years`` text such as ``(U 1873-1925, M 1873-1933, Z 1873-1933)``
    — date coverage per event, where U = Urodzenia (births), M = Małżeństwa,
    Z = Zgony.

So a single request per region yields everything; with ~22 regions and the
5s rate limit this script finishes in ~2 minutes.

Output columns:
  Miejscowość, Parafia, Rodzaj Księgi, Rok od, Rok do, voivodeship, parish_id

For now Miejscowość and Parafia hold the same value (the option text).
``parish_id`` is the event-specific rid, so the row can be plugged straight
back into a Geneteka search URL for that book.

Usage:
    uv run python scripts/geneteka_parish_books.py
    uv run python scripts/geneteka_parish_books.py --region 06mp
    uv run python scripts/geneteka_parish_books.py -o sources/geneteka.csv

The run is resumable: a sidecar ``<output>.progress`` file records which
region codes have been written. Re-running appends only the missing ones.
Delete the progress file (or pass ``--restart``) to rebuild from scratch.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://geneteka.genealodzy.pl/index.php"
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
    "voivodeship",
    "parish_id",
]

# Geneteka uses U / M / Z in data-years; we emit the Polish book-type labels
# used by the rest of the project (Chrzty / Śluby / Zgony).
EVENT_CATEGORIES: list[tuple[str, str, str]] = [
    # (data-attr, year-prefix in data-years, "Rodzaj Księgi" label)
    ("data-b", "U", "Chrzty"),
    ("data-s", "M", "Śluby"),
    ("data-d", "Z", "Zgony"),
]

# Matches "U 1873-1925" / "M 1729-1943" / "Z 1784-1945" inside data-years.
# Geneteka uses ASCII hyphens but tolerate en/em dashes just in case.
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

    def as_csv_row(self) -> dict[str, str | int]:
        return {
            "Miejscowość": self.miejscowosc,
            "Parafia": self.parafia,
            "Rodzaj Księgi": self.rodzaj_ksiegi,
            "Rok od": self.rok_od,
            "Rok do": self.rok_do,
            "voivodeship": self.voivodeship,
            "parish_id": self.parish_id,
        }


def fetch_region_page(
    session: requests.Session,
    *,
    region_code: str,
    timeout: float,
    verbose: bool,
) -> str:
    params = {"op": "gt", "lang": "pol", "bdm": "B", "w": region_code}
    if verbose:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        print(f"Fetching {BASE_URL}?{query}", file=sys.stderr)
    response = session.get(BASE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return response.text


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
        # The first option is the "Wszystkie miejscowości" placeholder whose
        # value is the bdm letter ("B"/"S"/"D"), not a numeric rid.
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
            rok_od = int(match.group(1))
            rok_do = int(match.group(2))
            rows.append(
                ParishBookRow(
                    miejscowosc=name,
                    parafia=name,
                    rodzaj_ksiegi=label,
                    rok_od=rok_od,
                    rok_do=rok_do,
                    voivodeship=voivodeship,
                    parish_id=rid,
                )
            )
    return rows


def progress_path_for(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".progress")


def load_completed(progress_path: Path) -> set[str]:
    if not progress_path.exists():
        return set()
    return {
        line.strip()
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


class ResumableCsvWriter:
    """Append rows per region and record completed region codes.

    A ``<output>.progress`` sidecar lists already-written region codes,
    one per line. When that file is present alongside the CSV the next
    run appends; otherwise the CSV is rewritten from scratch.
    """

    def __init__(self, output: Path, *, restart: bool) -> None:
        self.output = output
        self.progress = progress_path_for(output)
        if restart:
            if self.progress.exists():
                self.progress.unlink()
            if output.exists():
                output.unlink()
        self.completed: set[str] = load_completed(self.progress)
        output.parent.mkdir(parents=True, exist_ok=True)

        resuming = bool(self.completed) and output.exists()
        mode = "a" if resuming else "w"
        self._file = output.open(mode, encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDNAMES)
        if not resuming:
            self._writer.writeheader()
            self._file.flush()
            if self.progress.exists():
                self.progress.unlink()
            self.completed = set()

    def already_done(self, region_code: str) -> bool:
        return region_code in self.completed

    def write_region(self, region_code: str, rows: list[ParishBookRow]) -> None:
        for row in rows:
            self._writer.writerow(row.as_csv_row())
        self._file.flush()
        with self.progress.open("a", encoding="utf-8") as f:
            f.write(region_code + "\n")
        self.completed.add(region_code)

    def close(self) -> None:
        self._file.close()


def crawl(
    *,
    output: Path,
    timeout: float,
    delay_seconds: float,
    only_regions: list[str] | None,
    restart: bool,
    verbose: bool,
) -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # The first request also gives us the voivodeship dropdown, which we use
    # as the authoritative region list (any region picked from `--region` is
    # checked against it). Use 06mp as the seed since it always exists.
    seed_html = fetch_region_page(session, region_code="06mp", timeout=timeout, verbose=verbose)
    region_names = parse_regions(seed_html)

    if only_regions:
        unknown = [r for r in only_regions if r not in region_names]
        if unknown:
            print(
                f"Warning: unknown region codes ignored: {', '.join(unknown)}",
                file=sys.stderr,
            )
        codes = [r for r in only_regions if r in region_names]
    else:
        codes = sorted(region_names.keys())

    writer = ResumableCsvWriter(output, restart=restart)
    new_rows = 0
    try:
        for index, code in enumerate(codes, start=1):
            if writer.already_done(code):
                print(
                    f"Skipping {index}/{len(codes)}: {code} ({region_names[code]}) "
                    f"— already in {writer.progress.name}",
                    file=sys.stderr,
                )
                continue

            if code == "06mp" and index == 1:
                html = seed_html  # already fetched
            else:
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                html = fetch_region_page(
                    session, region_code=code, timeout=timeout, verbose=verbose
                )

            rows = parse_parishes(html, region_code=code, voivodeship=region_names[code])
            writer.write_region(code, rows)
            new_rows += len(rows)
            print(
                f"Crawled {index}/{len(codes)}: {code} ({region_names[code]}) "
                f"— {len(rows)} rows",
                file=sys.stderr,
            )
    finally:
        writer.close()

    return new_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Geneteka per-region parish book-range catalogue to CSV."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("sources/geneteka.csv"),
        help="CSV output path. Defaults to sources/geneteka.csv.",
    )
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
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds. Defaults to 30.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help=(
            "Seconds to wait between region requests. Defaults to 5 (matches "
            "the GENETEKA_MIN_INTERVAL default). Robots.txt asks for 120s; "
            "drop with care."
        ),
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Discard any existing progress file and rebuild from scratch.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every fetched URL to stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    new_rows = crawl(
        output=args.output,
        timeout=args.timeout,
        delay_seconds=args.delay,
        only_regions=args.regions,
        restart=args.restart,
        verbose=args.verbose,
    )
    print(f"Wrote {new_rows} new rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
