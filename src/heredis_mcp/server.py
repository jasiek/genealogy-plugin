"""FastMCP server exposing read-only Heredis genealogy tools."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastmcp import FastMCP

from heredis_mcp import queries
from heredis_mcp.db import open_ro
from heredis_mcp.models import (
    EventDetail,
    EventSearchResult,
    FamilyView,
    PersonDetail,
    PersonSearchResult,
    PlaceSearchResult,
    SourceSearchResult,
    SourceSummary,
)


def build_server(db_path: Path | str) -> FastMCP:
    """Construct a FastMCP server bound to a Heredis SQLite file.

    The connection is opened lazily per call so the server is safe to share
    across requests without sqlite3 thread-affinity headaches.
    """
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Heredis file not found: {db_path}")

    mcp = FastMCP(
        name="heredis-mcp",
        instructions=(
            "Read-only access to a Heredis genealogy database. Use search_persons "
            "and search_events to discover records, then get_person / get_family / "
            "get_event for details. Names and places are matched case- and "
            "accent-insensitively. Year filters are inclusive Gregorian years."
        ),
    )

    @contextmanager
    def conn() -> Iterator[sqlite3.Connection]:
        c = open_ro(db_path)
        try:
            yield c
        finally:
            c.close()

    @mcp.tool
    def search_persons(
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
        """Search persons by name, sex, birth/death year range, or place.

        - `name` matches either surname or given names. Use `surname` /
          `given_name` for targeted matches. All name matching is
          case- and diacritic-insensitive.
        - `sex` is "M", "F" or "U".
        - Year filters are inclusive Gregorian years.
        - `place` matches a city name on any associated event.
        - `limit` is capped at 100.
        """
        with conn() as c:
            return queries.search_persons(
                c,
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
    def get_person(code_id: int) -> PersonDetail | None:
        """Fetch a person by Heredis CodeID, with all events and unions."""
        with conn() as c:
            return queries.get_person(c, code_id)

    @mcp.tool
    def get_family(code_id: int) -> FamilyView | None:
        """Fetch a person plus parents, siblings, unions, and children in one call."""
        with conn() as c:
            return queries.get_family(c, code_id)

    @mcp.tool
    def search_events(
        event_type: int | None = None,
        title: str | None = None,
        place: str | None = None,
        person_id: int | None = None,
        after_year: int | None = None,
        before_year: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EventSearchResult:
        """Search events by type, title, place, person involvement, or date range.

        `person_id` matches both the event's owner and any participant in shared
        events (witnesses, godparents, etc.). Common `event_type` values: 4=Birth,
        8=Baptism, 12=Burial, 6=Death, 30=Residence, 61=Marriage.
        """
        with conn() as c:
            return queries.search_events(
                c,
                event_type=event_type,
                title=title,
                place=place,
                person_id=person_id,
                after_year=after_year,
                before_year=before_year,
                limit=limit,
                offset=offset,
            )

    @mcp.tool
    def get_event(code_id: int) -> EventDetail | None:
        """Fetch an event by CodeID, with participants for shared events."""
        with conn() as c:
            return queries.get_event(c, code_id)

    @mcp.tool
    def search_places(query: str, limit: int = 20, offset: int = 0) -> PlaceSearchResult:
        """Search places by city, department, region, or country (fuzzy / accent-insensitive)."""
        with conn() as c:
            return queries.search_places(c, query, limit=limit, offset=offset)

    @mcp.tool
    def search_sources(query: str, limit: int = 20, offset: int = 0) -> SourceSearchResult:
        """Search sources by title, document, or author."""
        with conn() as c:
            return queries.search_sources(c, query, limit=limit, offset=offset)

    @mcp.tool
    def get_source(code_id: int) -> SourceSummary | None:
        """Fetch a source by CodeID, including its repository title."""
        with conn() as c:
            return queries.get_source(c, code_id)

    return mcp
