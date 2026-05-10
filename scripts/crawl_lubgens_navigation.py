#!/usr/bin/env python3
"""Crawl Lubgens parish pages to a denormalized book-range CSV."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

BASE_URL = "https://regestry.lubgens.eu/news.php"
INDEX_URL = "https://regestry.lubgens.eu/druk_usz_v2_1.php"
FIELDNAMES = ["Miejscowość", "Parafia", "Rodzaj Księgi", "Rok od", "Rok do"]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CATEGORY_NAMES = {"u": "Chrzty", "s": "Śluby", "z": "Zgony"}
YEAR_RANGE_RE = re.compile(r"(\d{4})\s*[-–—]\s*(\d{4})")


@dataclass(frozen=True)
class ParishLink:
    miejscowosc: str
    label: str
    par_id: str
    url: str


@dataclass(frozen=True)
class LubgensBookRangeRow:
    miejscowosc: str
    parafia: str
    rodzaj_ksiegi: str
    rok_od: int
    rok_do: int

    def as_csv_row(self) -> dict[str, str | int]:
        return {
            "Miejscowość": self.miejscowosc,
            "Parafia": self.parafia,
            "Rodzaj Księgi": self.rodzaj_ksiegi,
            "Rok od": self.rok_od,
            "Rok do": self.rok_do,
        }


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_par_id(url: str) -> str:
    parsed = urlparse(url)
    values = parse_qs(parsed.query, keep_blank_values=True).get("par", [])
    return values[0] if values else ""


def fetch_page(
    session: requests.Session, url: str, timeout: float, *, verbose: bool = False
) -> str:
    if verbose:
        print(f"Fetching {url}", file=sys.stderr)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def iter_navigation_groups(navigation: Tag) -> list[tuple[str, Tag]]:
    groups: list[tuple[str, Tag]] = []
    for heading in navigation.find_all("h2", class_="head", recursive=False):
        sibling = heading.find_next_sibling()
        while sibling is not None and not (isinstance(sibling, Tag) and sibling.name == "ul"):
            sibling = sibling.find_next_sibling()
        if isinstance(sibling, Tag):
            groups.append((clean_text(heading.get_text(" ", strip=True)), sibling))
    return groups


def parse_parish_links(html: str, base_url: str = BASE_URL) -> list[ParishLink]:
    soup = BeautifulSoup(html, "html.parser")
    navigation = soup.select_one("#navigation")
    if navigation is None:
        raise ValueError("Could not find #navigation in Lubgens page")

    links: list[ParishLink] = []
    seen_urls: set[str] = set()
    for miejscowosc, list_node in iter_navigation_groups(navigation):
        for link in list_node.select("a.side[href]"):
            href = link.get("href", "")
            if not href:
                continue

            url = urljoin(base_url, href)
            par_id = extract_par_id(url)
            if not par_id or url in seen_urls:
                continue

            parish_label = link.select_one("span")
            label = clean_text(
                parish_label.get_text(" ", strip=True)
                if parish_label is not None
                else link.get_text(" ", strip=True)
            )
            links.append(
                ParishLink(
                    miejscowosc=miejscowosc.upper(),
                    label=label,
                    par_id=par_id,
                    url=url,
                )
            )
            seen_urls.add(url)

    return links


def parse_parish_name(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    parish_heading = soup.select_one(".mainbox .par")
    if parish_heading is None:
        return fallback

    text = clean_text(parish_heading.get_text(" ", strip=True))
    if "," not in text:
        return text or fallback

    place, parish_name = text.split(",", 1)
    parish_name = clean_text(parish_name)
    return parish_name or clean_text(place) or fallback


def parse_decades(html: str) -> dict[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    decades: dict[str, list[str]] = {}
    for category in CATEGORY_NAMES:
        box = soup.select_one(f"#decsbox{category}")
        if box is None:
            decades[category] = []
            continue

        category_decades: list[str] = []
        for span in box.select("span[id]"):
            span_id = span.get("id", "")
            if not span_id.startswith(category):
                continue
            decade = span_id[len(category) :]
            if decade.isdigit():
                category_decades.append(decade)
        decades[category] = category_decades

    return decades


def parse_years_from_index_html(html: str) -> list[int]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.indtbl")
    if table is None:
        return []

    header_cells = table.find_all("th")
    year_index = None
    for index, cell in enumerate(header_cells):
        if clean_text(cell.get_text(" ", strip=True)).upper() == "ROK":
            year_index = index
            break
    if year_index is None:
        return []

    years: list[int] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) <= year_index:
            continue
        year_text = clean_text(cells[year_index].get_text(" ", strip=True))
        if year_text.isdigit():
            years.append(int(year_text))

    return years


def fetch_index_years(
    session: requests.Session,
    *,
    par_id: str,
    category: str,
    decade: str,
    timeout: float,
    verbose: bool,
) -> list[int]:
    query = urlencode({"par": par_id, "act": category, "decade": decade})
    html = fetch_page(session, f"{INDEX_URL}?{query}", timeout, verbose=verbose)
    return parse_years_from_index_html(html)


def decade_bounds(decades: list[str]) -> tuple[int, int] | None:
    ranges: list[tuple[int, int]] = []
    for decade in decades:
        start = int(decade) * 10
        text = f"{start} - {start + 9}"
        if match := YEAR_RANGE_RE.search(text):
            ranges.append((int(match.group(1)), int(match.group(2))))

    if not ranges:
        return None
    return min(start for start, _ in ranges), max(end for _, end in ranges)


def crawl_parish(
    session: requests.Session,
    parish_link: ParishLink,
    *,
    timeout: float,
    delay_seconds: float,
    exact_years: bool,
    verbose: bool,
) -> list[LubgensBookRangeRow]:
    parish_html = fetch_page(session, parish_link.url, timeout, verbose=verbose)
    parish_name = parse_parish_name(parish_html, fallback=parish_link.label)
    decades_by_category = parse_decades(parish_html)

    rows: list[LubgensBookRangeRow] = []
    for category, decades in decades_by_category.items():
        if not decades:
            continue

        if exact_years:
            years: list[int] = []
            for decade in decades:
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                years.extend(
                    fetch_index_years(
                        session,
                        par_id=parish_link.par_id,
                        category=category,
                        decade=decade,
                        timeout=timeout,
                        verbose=verbose,
                    )
                )
            if not years:
                continue
            rok_od, rok_do = min(years), max(years)
        else:
            bounds = decade_bounds(decades)
            if bounds is None:
                continue
            rok_od, rok_do = bounds

        rows.append(
            LubgensBookRangeRow(
                miejscowosc=parish_link.miejscowosc,
                parafia=parish_name,
                rodzaj_ksiegi=CATEGORY_NAMES[category],
                rok_od=rok_od,
                rok_do=rok_do,
            )
        )

    return rows


def progress_path_for(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".progress")


def load_completed_par_ids(progress_path: Path) -> set[str]:
    if not progress_path.exists():
        return set()
    return {
        line.strip()
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


class ResumableCsvWriter:
    """Append rows to a CSV per parish and record completed par_ids.

    A sidecar ``<output>.progress`` file tracks which parishes have been
    fully written. Presence of the progress file indicates a resumable
    run: the existing CSV is appended to. Without it, the CSV is
    rewritten from scratch.
    """

    def __init__(self, output: Path) -> None:
        self.output = output
        self.progress = progress_path_for(output)
        self.completed: set[str] = load_completed_par_ids(self.progress)
        output.parent.mkdir(parents=True, exist_ok=True)

        resuming = bool(self.completed) and output.exists()
        mode = "a" if resuming else "w"
        self._file = output.open(mode, encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDNAMES)
        if not resuming:
            self._writer.writeheader()
            self._file.flush()
            # Reset progress to match a fresh CSV.
            if self.progress.exists():
                self.progress.unlink()
            self.completed = set()

    def already_done(self, par_id: str) -> bool:
        return par_id in self.completed

    def write_parish(self, par_id: str, rows: list[LubgensBookRangeRow]) -> None:
        for row in rows:
            self._writer.writerow(row.as_csv_row())
        self._file.flush()
        with self.progress.open("a", encoding="utf-8") as f:
            f.write(par_id + "\n")
        self.completed.add(par_id)

    def close(self) -> None:
        self._file.close()


def crawl(
    *,
    base_url: str,
    output: Path,
    timeout: float,
    delay_seconds: float,
    exact_years: bool,
    max_parishes: int | None,
    verbose: bool,
) -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    parish_links = parse_parish_links(
        fetch_page(session, base_url, timeout, verbose=verbose), base_url=base_url
    )
    if max_parishes is not None:
        parish_links = parish_links[:max_parishes]

    writer = ResumableCsvWriter(output)
    new_rows = 0
    fetched = 0
    try:
        for index, parish_link in enumerate(parish_links, start=1):
            if writer.already_done(parish_link.par_id):
                print(
                    f"Skipping {index}/{len(parish_links)}: {parish_link.label} "
                    f"(already in {writer.progress.name})",
                    file=sys.stderr,
                )
                continue
            if delay_seconds > 0 and fetched > 0:
                time.sleep(delay_seconds)
            fetched += 1
            rows = crawl_parish(
                session,
                parish_link,
                timeout=timeout,
                delay_seconds=delay_seconds,
                exact_years=exact_years,
                verbose=verbose,
            )
            writer.write_parish(parish_link.par_id, rows)
            new_rows += len(rows)
            print(
                f"Crawled {index}/{len(parish_links)}: {parish_link.label} "
                f"(+{len(rows)} rows, {new_rows} new total)",
                file=sys.stderr,
            )
    finally:
        writer.close()

    return new_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl Lubgens parish category date ranges to CSV."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("sources/lubgens_parish_books.csv"),
        help="CSV output path. Defaults to sources/lubgens_parish_books.csv.",
    )
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"Navigation page URL. Defaults to {BASE_URL}",
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
        default=0.2,
        help="Seconds to wait between requests. Defaults to 0.2.",
    )
    parser.add_argument(
        "--max-parishes",
        type=int,
        default=None,
        help="Optional parish limit for testing.",
    )
    parser.add_argument(
        "--decade-bounds",
        action="store_true",
        help="Use decade bucket bounds instead of fetching AJAX rows for exact years.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every crawled URL to stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    new_rows = crawl(
        base_url=args.url,
        output=args.output,
        timeout=args.timeout,
        delay_seconds=args.delay,
        exact_years=not args.decade_bounds,
        max_parishes=args.max_parishes,
        verbose=args.verbose,
    )
    print(f"Wrote {new_rows} new rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
