"""Parse a Genealogy Indexer search-results page into typed records.

The upstream returns a full HTML document. The match count is a
``Matches Found: N`` line, and the hits live in ``<ol id="search_results">``
as one ``<li>`` per source page:

* ``<h2>`` — an ``<a target=_blank>`` to the scanned page (the link text is
  the source title) plus a ``<span class="i_num">image N</span>``.
* one or more ``<div class="mb-2 snippet">`` — either a run of OCR text with
  the matched terms in ``<span class="hl">``, or a ``<table>`` of directory
  rows (a header ``<tr class="h">`` / ``<tr class="h d-none">`` plus data
  rows).
* ``<div class="rf">`` — an "About this source" dropdown carrying the
  original title, the hosting library (``Images From:``), the Genealogy
  Indexer source ID, and the date the source was added.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from genealogy_mcp.sources.genealogyindexer.models import (
    GenealogyIndexerMatch,
    GenealogyIndexerSearchResult,
)

# The page must carry one of these once it has rendered a search; their
# absence means the layout changed (or the response was truncated).
_MATCHES_RE = re.compile(r"Matches\s+Found:\s*([\d,]+)", re.IGNORECASE)
_NO_MATCH_RE = re.compile(r"No\s+matches", re.IGNORECASE)


def _resolve_url(href: str | None, base_url: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return href


def _snippet_text(sn: Tag) -> str:
    """Flatten a text snippet, wrapping the matched terms in ``**bold**``."""
    for hl in sn.find_all("span", class_="hl"):
        hl.replace_with("**" + hl.get_text(" ", strip=True) + "**")
    return re.sub(r"\s+", " ", sn.get_text(" ")).strip()


def _parse_table(table: Tag) -> list[dict[str, str]]:
    """Turn a directory table into one dict per data row (header-keyed)."""
    for hl in table.find_all("span", class_="hl"):
        hl.replace_with(hl.get_text(" ", strip=True))

    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for tr in table.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        classes = tr.get("class") or []
        if "h" in classes:
            if header is None:
                header = cells
            continue
        if not any(cells):
            continue
        if header and len(header) == len(cells):
            row = {k: v for k, v in zip(header, cells) if v}
        else:
            row = {str(i): v for i, v in enumerate(cells) if v}
        if row:
            rows.append(row)
    return rows


def _parse_source_meta(rf: Tag, base_url: str) -> dict[str, object]:
    out: dict[str, object] = {}
    scope = rf.find("div", class_="dropdown-menu")
    target = scope if isinstance(scope, Tag) else rf
    for p in target.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text.startswith("Original Title:"):
            out["source_title"] = text.split(":", 1)[1].strip() or None
        elif text.startswith("Images From:"):
            a = p.find("a", href=True)
            if isinstance(a, Tag):
                out["images_from"] = a.get_text(" ", strip=True) or None
                out["images_from_url"] = _resolve_url(a["href"], base_url)
            else:
                out["images_from"] = text.split(":", 1)[1].strip() or None
        elif text.startswith("Genealogy Indexer ID:"):
            out["source_id"] = text.split(":", 1)[1].strip() or None
        elif text.startswith("Added to Genealogy Indexer:"):
            out["date_added"] = text.split(":", 1)[1].strip() or None
    return out


def _parse_li(li: Tag, base_url: str) -> GenealogyIndexerMatch:
    fields: dict[str, object] = {}

    h2 = li.find("h2")
    if isinstance(h2, Tag):
        a = h2.find("a", href=True)
        if isinstance(a, Tag):
            fields["title"] = a.get_text(" ", strip=True) or None
            fields["scan_url"] = _resolve_url(a["href"], base_url)
        span = h2.find("span", class_="i_num")
        if isinstance(span, Tag):
            label = span.get_text(" ", strip=True)
            fields["image_label"] = label or None
            m = re.search(r"(\d+)", label)
            if m:
                fields["image_number"] = int(m.group(1))

    snippets: list[str] = []
    entries: list[dict[str, str]] = []
    for sn in li.find_all("div", class_="snippet"):
        if not isinstance(sn, Tag):
            continue
        table = sn.find("table")
        if isinstance(table, Tag):
            entries.extend(_parse_table(table))
        else:
            text = _snippet_text(sn)
            if text:
                snippets.append(text)
    fields["snippets"] = snippets
    fields["entries"] = entries

    rf = li.find("div", class_="rf")
    if isinstance(rf, Tag):
        fields.update(_parse_source_meta(rf, base_url))

    return GenealogyIndexerMatch(**fields)  # type: ignore[arg-type]


def parse_search_response(
    body: str,
    *,
    query: str | None = None,
    base_url: str = "https://genealogyindexer.org",
    max_results: int | None = None,
) -> GenealogyIndexerSearchResult:
    """Parse a Genealogy Indexer results page.

    Raises ``ValueError`` if the page shows neither a "Matches Found" count
    nor a "No matches" notice — which means the layout changed or the
    response was truncated. A genuine empty result set returns an empty
    ``items`` list.
    """
    mf = _MATCHES_RE.search(body)
    if mf is None and _NO_MATCH_RE.search(body) is None:
        raise ValueError(
            "Genealogy Indexer response carries no 'Matches Found' or 'No "
            "matches' marker; the page layout may have changed or the "
            "response was truncated."
        )
    total = int(mf.group(1).replace(",", "")) if mf else 0

    soup = BeautifulSoup(body, "html.parser")
    ol = soup.find("ol", id="search_results")

    items: list[GenealogyIndexerMatch] = []
    if isinstance(ol, Tag):
        for li in ol.find_all("li", recursive=False):
            if isinstance(li, Tag):
                items.append(_parse_li(li, base_url))

    # Each rendered match is one snippet or one table row; sum these to learn
    # how many of the upstream's ``total`` matches actually made it into the
    # page (it caps the listing for very common terms).
    shown = sum(len(it.snippets) + len(it.entries) for it in items)
    truncated = total > shown

    if max_results is not None and len(items) > max_results:
        items = items[:max_results]
        truncated = True

    return GenealogyIndexerSearchResult(
        query=query,
        total=total or shown,
        returned=len(items),
        truncated=truncated,
        items=items,
    )
