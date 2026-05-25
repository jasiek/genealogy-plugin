"""Register the BaSIA research tool on a FastMCP server.

BaSIA (https://basia.famula.pl) is the WTG-Gniazdo / PSNC "Baza Systemu
Indeksacji Archiwalnej" — an index of archival vital records and other
documents from Wielkopolska (Greater Poland), mostly 18th-20th c. This is a
*research* tier source: candidate matches the agent should propose, never
write back without user review. Tool names are prefixed ``basia_``.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from genealogy_mcp.sources.basia.client import BasiaClient, BasiaConfig
from genealogy_mcp.sources.basia.constants import DEFAULT_SIMILARITY
from genealogy_mcp.sources.basia.models import BasiaSearchResult

Sex = Literal["any", "male", "female"]
Relation = Literal["any", "parent_or_spouse", "child", "other"]
RecordTypeArg = Literal["any", "birth", "marriage", "death", "banns", "other"]
UnitType = Literal["any", "usc", "catholic", "evangelical", "other"]


def register(mcp: FastMCP, config: BasiaConfig | None = None) -> BasiaClient:
    """Register all `basia_*` tools. Returns the client so the caller can close it."""
    client = BasiaClient(config)

    @mcp.tool
    def basia_search(
        surname: str | None = None,
        given_name: str | None = None,
        sex: Sex = "any",
        relation: Relation = "any",
        similarity: int = DEFAULT_SIMILARITY,
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
        distance_km: int = 10,
        record_type: RecordTypeArg = "any",
        unit_type: UnitType = "any",
        max_results: int = 200,
    ) -> BasiaSearchResult:
        """Search BaSIA (Wielkopolska archival index) for indexed records.

        BaSIA runs a *fuzzy* name match over its whole 6.6M-entry base
        server-side, so the search is SLOW and broad queries can time out
        upstream (a bare common surname may take well over a minute or
        come back truncated, which raises an error asking you to narrow
        the query). Always narrow where you can — it is both faster and
        more precise:

        - ``surname`` / ``given_name`` — at least one of these, or
          ``place``, is required. Both are matched fuzzily.
        - ``similarity`` (0-100, default 60) is the minimum match score;
          raise it to tighten and speed up, lower it to catch variant
          spellings (slower).
        - ``from_year`` / ``to_year`` constrain the act year (the corpus
          spans roughly 1577 onward).
        - ``record_type`` — ``birth``, ``marriage``, ``death``, ``banns``,
          or ``other``; filtering here cuts search time substantially.
        - ``unit_type`` — ``usc`` (civil registry), ``catholic``,
          ``evangelical``, or ``other``.
        - ``sex`` and ``relation`` (the person's role: a spouse/parent, a
          child, or other) further constrain the principal person.
        - ``place`` matches a locality (optionally with ``distance_km``
          radius).
        - ``max_results`` caps returned items (default 200); when the page
          held more, ``truncated`` is True and ``total`` reports the full
          count.

        Each item carries the place, parish/registry, year, principal
        person (with best-effort given/surname split, age, parents, and
        spouse), the fuzzy ``similarity`` score, a ``scan_url`` to the
        digitised image when one was indexed (szukajwarchiwach /
        familysearch), and a stable ``permalink``. Results are research
        candidates — cross-check against the user's verified facts
        (``heredis_search_persons``) before relying on them.
        """
        return client.search(
            surname=surname,
            given_name=given_name,
            sex=sex,
            relation=relation,
            similarity=similarity,
            from_year=from_year,
            to_year=to_year,
            place=place,
            distance_km=distance_km,
            record_type=record_type,
            unit_type=unit_type,
            max_results=max_results,
        )

    return client
