"""Register the Lubgens research tool on a FastMCP server.

Lubgens (https://regestry.lubgens.eu) is the Lubelskie Korzenie regional
index of parish registers and USC records covering the Lublin region
and adjacent areas. This is a *research* tier source: candidate matches
the agent should propose, never write back without user review. Tool
names are prefixed ``lubgens_``.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from polish_genealogy_mcp.sources.lubgens.client import LubgensClient, LubgensConfig
from polish_genealogy_mcp.sources.lubgens.models import LubgensSearchResult

WildMode = Literal["prefix", "exact", "substring"]
RecordTypeArg = Literal["birth", "marriage", "death"]


def register(mcp: FastMCP, config: LubgensConfig | None = None) -> LubgensClient:
    """Register all `lubgens_*` tools. Returns the client so the caller can close it."""
    client = LubgensClient(config)

    @mcp.tool
    def lubgens_search(
        surname: str | None = None,
        given_name: str | None = None,
        record_types: list[RecordTypeArg] | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        wildmode: WildMode = "prefix",
    ) -> LubgensSearchResult:
        """Search the Lubelskie Korzenie regional index for vital records.

        Returns up to 500 rows per record type (the upstream's
        per-category cap). When a category is truncated, the
        ``truncated`` map will have ``True`` for that record type and
        narrowing the query (year range, exact name, given name) is
        the only way to see further matches.

        - ``surname`` / ``given_name`` are matched against the indexed
          spelling; ``wildmode`` controls how:
            * ``prefix`` (default) — match the start of the word.
            * ``exact`` — literal match.
            * ``substring`` — match anywhere inside the word.
        - ``record_types`` defaults to all three (birth, marriage,
          death). Pass a subset to skip categories.
        - Each result row carries ``scan_url`` when the index entry
          links to a digitised image (typically on
          ``szukajwarchiwach.gov.pl`` or ``familysearch.org``).
        - Parents are best-effort extracted from the ``UWAGI`` cell
          into ``father_name`` / ``mother_name``; the raw note text
          remains in ``notes`` (which for marriages also contains the
          bride's parents under the ``Ona-`` marker).
        """
        return client.search(
            surname=surname,
            given_name=given_name,
            record_types=record_types or ["birth", "marriage", "death"],
            from_year=from_year,
            to_year=to_year,
            wildmode=wildmode,
        )

    return client
