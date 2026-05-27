"""Register the Genealogy Indexer research tool on a FastMCP server.

Genealogy Indexer (https://genealogyindexer.org) is a full-text OCR search
engine over digitised historical directories, yizkor (Holocaust memorial)
books, military lists, community/personal histories, and school sources from
Central and Eastern Europe and beyond. This is a *research* tier source:
candidate mentions the agent should propose, never write back without user
review. Tool names are prefixed ``genealogyindexer_``.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from genealogy_mcp.sources.genealogyindexer.client import (
    GenealogyIndexerClient,
    GenealogyIndexerConfig,
)
from genealogy_mcp.sources.genealogyindexer.constants import DEFAULT_MAX_RESULTS
from genealogy_mcp.sources.genealogyindexer.models import GenealogyIndexerSearchResult

Collection = Literal["any", "directories", "yizkor", "military", "history", "school"]
DateRange = Literal["any", "to_1918", "1919_1945", "from_1946"]
MatchMode = Literal["regular", "soundex", "ocr"]
SortMode = Literal["regular", "newest", "alphabetic"]
Transliteration = Literal[
    "none",
    "add_cyrillic",
    "add_cyrillic_hebrew",
    "add_hebrew",
    "only_cyrillic",
    "only_cyrillic_hebrew",
    "only_hebrew",
]


def register(mcp: FastMCP, config: GenealogyIndexerConfig | None = None) -> GenealogyIndexerClient:
    """Register all `genealogyindexer_*` tools. Returns the client so the caller can close it."""
    client = GenealogyIndexerClient(config)

    @mcp.tool
    def genealogyindexer_search(
        term: str,
        place: str = "any",
        collection: Collection = "any",
        date: DateRange = "any",
        match: MatchMode = "regular",
        sort: SortMode = "regular",
        transliteration: Transliteration = "none",
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> GenealogyIndexerSearchResult:
        """Full-text search of Genealogy Indexer's digitised historical sources.

        This searches OCR'd page *text*, not a structured vital-record index,
        so it complements geneteka / basia / lubgens: a surname surfaces
        wherever it was printed — a 1930s business or address directory, a
        yizkor memorial roll, a military or voter list, a school yearbook —
        each with a snippet of context and a link to the scanned page. The
        corpus is Central/Eastern Europe-centred (strong Polish, Galician,
        German, and Jewish coverage) but spans many countries.

        - ``term`` (required) is matched against the full page text and
          accepts the upstream query operators verbatim:
          ``"exact phrase"``; ``wild*`` / ``*card``; ``a | b`` (OR);
          ``a b`` (AND, same page); ``-"excluded phrase"`` (NOT);
          ``"two words"~4`` (proximity); ``[s]urname`` (force Soundex on a
          letter); ``katz {d82,y17}`` (restrict to source IDs);
          ``kalter {1903-1923}`` (restrict to a year range).
        - ``place`` narrows by the source's geography — a country name
          (e.g. ``"Poland"``, ``"Germany"``, ``"Ukraine"``), ``"Galicia"`` /
          ``"Silesia"`` / ``"Bessarabia"`` for the cross-border regions, or a
          raw scope code from the site's Place dropdown for a sub-region/city.
        - ``collection`` limits to ``directories``, ``yizkor``, ``military``,
          ``history``, or ``school`` sources.
        - ``date`` buckets by publication era: ``to_1918``, ``1919_1945``,
          or ``from_1946``.
        - ``match`` — ``regular``, ``soundex`` (Daitch-Mokotoff, for spelling
          variants), or ``ocr`` (tolerant of scanning errors).
        - ``transliteration`` adds/forces Latin↔Cyrillic/Hebrew variants;
          defaults to ``none`` (the website itself defaults to add-Cyrillic).
        - ``max_results`` caps returned source-page items (default 100).

        Each item is one source *page*: its title, an ``image_label``, a
        ``scan_url`` to the digitised image, the hosting library, and either
        text ``snippets`` (matched terms in ``**bold**``) or structured
        ``entries`` (directory rows keyed by column). ``total`` is the site's
        match count and can exceed the returned item count (hits are grouped
        by page, and very common terms are capped — ``truncated`` flags that).
        Results are research candidates — cross-check against the user's
        verified facts (``heredis_search_persons``) before relying on them.
        """
        return client.search(
            term=term,
            place=place,
            collection=collection,
            date=date,
            match=match,
            sort=sort,
            transliteration=transliteration,
            max_results=max_results,
        )

    return client
