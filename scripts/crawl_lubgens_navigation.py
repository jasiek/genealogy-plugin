#!/usr/bin/env python3
"""Crawl Lubgens parish pages to a denormalized book-range CSV.

Usage:
    uv run python scripts/crawl_lubgens_navigation.py                              # stdout
    uv run python scripts/crawl_lubgens_navigation.py -o sources/lubgens_parish_books.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    ResumableCsvSink,
    add_common_args,
    eprint,
    make_session,
)

BASE_URL = "https://regestry.lubgens.eu/news.php"
INDEX_URL = "https://regestry.lubgens.eu/druk_usz_v2_1.php"
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

    def as_csv_row(self) -> dict[str, object]:
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
    """Fetch ``url`` and return the body.

    Kept as a local helper (rather than delegating to ``_common.fetch_text``)
    because ``tests/test_crawl_lubgens_navigation.py`` exercises this
    function with a minimal stub Session — and pins the exact stderr text
    emitted with ``verbose=True``.
    """
    if verbose:
        eprint(f"Fetching {url}")
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


def crawl(
    *,
    base_url: str,
    output: Path | None,
    user_agent: str | None,
    timeout: float,
    delay_seconds: float,
    exact_years: bool,
    max_parishes: int | None,
    restart: bool,
    verbose: bool,
) -> int:
    session = make_session(user_agent)

    parish_links = parse_parish_links(
        fetch_page(session, base_url, timeout, verbose=verbose), base_url=base_url
    )
    if max_parishes is not None:
        parish_links = parish_links[:max_parishes]

    new_rows = 0
    fetched = 0
    with ResumableCsvSink(output, BASE_FIELDS, restart=restart) as sink:
        for index, parish_link in enumerate(parish_links, start=1):
            if sink.already_done(parish_link.par_id):
                eprint(f"Skipping {index}/{len(parish_links)}: {parish_link.label} (already done)")
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
            n = sink.write_unit(parish_link.par_id, (r.as_csv_row() for r in rows))
            new_rows += n
            eprint(
                f"Crawled {index}/{len(parish_links)}: {parish_link.label} "
                f"(+{n} rows, {new_rows} new total)"
            )

    return new_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl Lubgens parish category date ranges to CSV."
    )
    add_common_args(parser, default_delay=0.2, supports_resume=True)
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"Navigation page URL (default: {BASE_URL}).",
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.input_html is not None:
        # Offline: treat the fixture as a *parish* page (the navigation
        # page alone produces no rows — it just lists parish links).
        # Decade-bounds mode is forced because exact-years parsing
        # requires extra per-decade fetches.
        parish_html = args.input_html.read_text(encoding="utf-8")
        parish_name = parse_parish_name(parish_html, fallback=args.input_html.stem)
        decades_by_category = parse_decades(parish_html)
        rows: list[LubgensBookRangeRow] = []
        for category, decades in decades_by_category.items():
            if not decades:
                continue
            bounds = decade_bounds(decades)
            if bounds is None:
                continue
            rok_od, rok_do = bounds
            rows.append(
                LubgensBookRangeRow(
                    miejscowosc=parish_name.upper(),
                    parafia=parish_name,
                    rodzaj_ksiegi=CATEGORY_NAMES[category],
                    rok_od=rok_od,
                    rok_do=rok_do,
                )
            )
        with ResumableCsvSink(args.output, BASE_FIELDS, restart=args.restart) as sink:
            n = sink.write_unit(args.input_html.stem, (r.as_csv_row() for r in rows))
        eprint(
            f"{parish_name} (offline): {n} rows"
            + (f" → {args.output}" if args.output else " → stdout")
        )
        return 0

    new_rows = crawl(
        base_url=args.url,
        output=args.output,
        user_agent=args.user_agent,
        timeout=args.timeout,
        delay_seconds=args.delay,
        exact_years=not args.decade_bounds,
        max_parishes=args.max_parishes,
        restart=args.restart,
        verbose=args.verbose,
    )
    eprint(f"Wrote {new_rows} new rows" + (f" to {args.output}" if args.output else " to stdout"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
