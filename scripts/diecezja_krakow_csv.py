#!/usr/bin/env python3
"""Crawl Archiwum Archidiecezji Krakowskiej metryka pages to CSV.

Usage:
    uv run python scripts/diecezja_krakow_csv.py                   # stdout
    uv run python scripts/diecezja_krakow_csv.py -o krakow.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from polish_genealogy_mcp.scrapers.common import (
    BASE_FIELDS,
    CsvSink,
    add_common_args,
    eprint,
    fetch_text,
    make_session,
    parse_year_ranges,
)

BASE_URL = "https://archiwum.diecezja.pl/metryka/"
PAGE_URL_RE = re.compile(r"/metryka/page/(\d+)/")


@dataclass(frozen=True)
class MetrykaRow:
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


def normalize_label(text: str) -> str:
    return clean_text(text).rstrip(":").strip()


def page_url(base_url: str, page_number: int) -> str:
    base_url = base_url.rstrip("/") + "/"
    if page_number == 1:
        return base_url
    return urljoin(base_url, f"page/{page_number}/")


def discover_last_page(soup: BeautifulSoup) -> int:
    pages = [1]
    for link in soup.select(".pagination a[href]"):
        href = link.get("href", "")
        if match := PAGE_URL_RE.search(href):
            pages.append(int(match.group(1)))
    return max(pages)


def text_until_next_br(label: Tag) -> str:
    pieces: list[str] = []
    for sibling in label.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "br":
            break
        if isinstance(sibling, NavigableString):
            pieces.append(str(sibling))
        elif isinstance(sibling, Tag):
            pieces.append(sibling.get_text(" ", strip=True))
    return clean_text(" ".join(pieces))


def parse_rows(html: str) -> list[MetrykaRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[MetrykaRow] = []

    for item in soup.select("#blog .accordion .ac-item"):
        title = item.select_one("h2.ac-title")
        content = item.select_one(".ac-content")
        parish_heading = content.select_one("h3") if content else None
        parish_name = parish_heading.select_one("strong") if parish_heading else None
        if not title or not content or not parish_name:
            continue

        miejscowosc = clean_text(title.get_text(" ", strip=True)).upper()
        parafia = clean_text(parish_name.get_text(" ", strip=True))

        for label in content.find_all("strong"):
            if label.find_parent("h3") is not None:
                continue

            rodzaj_ksiegi = normalize_label(label.get_text(" ", strip=True))
            if rodzaj_ksiegi.lower() == "uwagi":
                continue

            for rok_od, rok_do in parse_year_ranges(text_until_next_br(label)):
                rows.append(
                    MetrykaRow(
                        miejscowosc=miejscowosc,
                        parafia=parafia,
                        rodzaj_ksiegi=rodzaj_ksiegi,
                        rok_od=rok_od,
                        rok_do=rok_do,
                    )
                )

    return rows


def crawl(
    *,
    base_url: str,
    user_agent: str | None,
    delay_seconds: float,
    timeout: float,
    max_pages: int | None,
    verbose: bool,
) -> list[MetrykaRow]:
    session = make_session(user_agent)

    first_html = fetch_text(session, page_url(base_url, 1), timeout=timeout, verbose=verbose)
    first_soup = BeautifulSoup(first_html, "html.parser")
    last_page = discover_last_page(first_soup)
    if max_pages is not None:
        last_page = min(last_page, max_pages)

    rows = parse_rows(first_html)
    for page_number in range(2, last_page + 1):
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        url = page_url(base_url, page_number)
        rows.extend(parse_rows(fetch_text(session, url, timeout=timeout, verbose=verbose)))

    return rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl https://archiwum.diecezja.pl/metryka/ to CSV."
    )
    add_common_args(parser, default_delay=0.5)
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Base listing URL (default: {BASE_URL}).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page limit for testing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.input_html is not None:
        rows = parse_rows(args.input_html.read_text(encoding="utf-8"))
    else:
        rows = crawl(
            base_url=args.base_url,
            user_agent=args.user_agent,
            delay_seconds=args.delay,
            timeout=args.timeout,
            max_pages=args.max_pages,
            verbose=args.verbose,
        )
    with CsvSink(args.output, BASE_FIELDS) as sink:
        for row in rows:
            sink.write_row(row.as_csv_row())
    eprint(f"Wrote {len(rows)} rows" + (f" to {args.output}" if args.output else " to stdout"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
