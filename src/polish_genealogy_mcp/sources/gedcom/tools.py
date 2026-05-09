"""Register `gedcom_*` tools that query an in-memory GEDCOM file.

The GEDCOM source is a *verified facts* tier alongside heredis: data the
user has researched and exported into their own file. The file is loaded
into memory once at server startup; all queries are pure dict/list scans.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from polish_genealogy_mcp.sources.gedcom import queries
from polish_genealogy_mcp.sources.gedcom.models import (
    EventDetail,
    EventSearchResult,
    FamilyView,
    PersonDetail,
    PersonSearchResult,
    PlaceSearchResult,
    SourceSearchResult,
    SourceSummary,
)
from polish_genealogy_mcp.sources.gedcom.parser import load


def register(mcp: FastMCP, gedcom_path: Path | str) -> None:
    """Register all `gedcom_*` tools, bound to a specific .ged file."""
    store = load(gedcom_path)

    @mcp.tool
    def gedcom_search_persons(
        name: str | None = None,
        surname: str | None = None,
        given_name: str | None = None,
        sex: str | None = None,
        born_after: int | None = None,
        born_before: int | None = None,
        died_after: int | None = None,
        died_before: int | None = None,
        place: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PersonSearchResult:
        """Search persons in the loaded GEDCOM file (verified facts).

        - `name` matches surname or given names. Use `surname` / `given_name`
          for targeted matches. Matching is case- and diacritic-insensitive.
        - `sex` is "M", "F" or "U".
        - Year filters use the year extracted from the event DATE tag.
        - `place` matches a PLAC string on any of the person's events.
        - `limit` is capped at 100.
        """
        return queries.search_persons(
            store,
            name=name,
            surname=surname,
            given_name=given_name,
            sex=sex,
            born_after=born_after,
            born_before=born_before,
            died_after=died_after,
            died_before=died_before,
            place=place,
            limit=limit,
            offset=offset,
        )

    @mcp.tool
    def gedcom_get_person(person_id: str) -> PersonDetail | None:
        """Fetch a person by GEDCOM xref id (e.g. ``@I123@``), with all events and unions."""
        return queries.get_person(store, person_id)

    @mcp.tool
    def gedcom_get_family(person_id: str) -> FamilyView | None:
        """Fetch a person plus parents, siblings, unions, and children in one call."""
        return queries.get_family(store, person_id)

    @mcp.tool
    def gedcom_search_events(
        tag: str | None = None,
        title: str | None = None,
        place: str | None = None,
        person_id: str | None = None,
        after_year: int | None = None,
        before_year: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EventSearchResult:
        """Search events by GEDCOM tag, title, place, person, or year range.

        Common `tag` values: BIRT, CHR, BAPM, DEAT, BURI, MARR, RESI, OCCU,
        EMIG, IMMI, CENS. Tags are matched case-insensitively against the
        upper-case GEDCOM tag.
        """
        return queries.search_events(
            store,
            tag=tag,
            title=title,
            place=place,
            person_id=person_id,
            after_year=after_year,
            before_year=before_year,
            limit=limit,
            offset=offset,
        )

    @mcp.tool
    def gedcom_get_event(event_id: str) -> EventDetail | None:
        """Fetch an event by its synthetic id (e.g. ``@I1@:BIRT`` or ``@F1@:MARR``)."""
        return queries.get_event(store, event_id)

    @mcp.tool
    def gedcom_search_places(query: str, limit: int = 20, offset: int = 0) -> PlaceSearchResult:
        """Search PLAC strings referenced anywhere in the GEDCOM (accent-insensitive)."""
        return queries.search_places(store, query, limit=limit, offset=offset)

    @mcp.tool
    def gedcom_search_sources(query: str, limit: int = 20, offset: int = 0) -> SourceSearchResult:
        """Search GEDCOM sources by title, author, or publication."""
        return queries.search_sources(store, query, limit=limit, offset=offset)

    @mcp.tool
    def gedcom_get_source(source_id: str) -> SourceSummary | None:
        """Fetch a GEDCOM source by xref id (e.g. ``@S1@``), including its repository title."""
        return queries.get_source(store, source_id)
