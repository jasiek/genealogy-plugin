"""Register Geneteka research tools on a FastMCP server.

Geneteka (https://geneteka.genealodzy.pl) is the Polish Genealogical Society's
parish-record index — births, marriages, and deaths transcribed by volunteers.
This source is the *research* tier: candidates the user evaluates before
committing anything to Heredis. Tool names are prefixed `geneteka_`.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from genealogy_mcp.sources.geneteka.client import GenetekaClient, GenetekaConfig
from genealogy_mcp.sources.geneteka.models import (
    GenetekaRecord,
    GenetekaRegion,
    GenetekaSearchResult,
    RecordType,
)
from genealogy_mcp.sources.geneteka.parser import parse_rows, parse_total
from genealogy_mcp.sources.geneteka.regions import get_regions


def register(mcp: FastMCP, config: GenetekaConfig | None = None) -> GenetekaClient:
    """Register all `geneteka_*` tools. Returns the client so the caller can close it."""
    client = GenetekaClient(config)

    @mcp.tool
    def geneteka_list_regions() -> list[GenetekaRegion]:
        """List Geneteka region codes (voivodeships + former eastern lands).

        The list is fetched live from Geneteka and cached on disk for 7 days
        (override via `GENETEKA_REGIONS_TTL_DAYS`). On any failure we fall
        back to a stale cache, then to a hardcoded built-in list, so the
        tool never breaks. The `code` value is what every other geneteka
        tool expects as `region`. Names are in Polish to match the UI.
        """
        regions = get_regions(client)
        return [GenetekaRegion(code=c, name=n) for c, n in regions.items()]

    @mcp.tool
    def geneteka_search(
        record_type: Literal["birth", "marriage", "death"],
        region: str,
        surname: str,
        given_name: str | None = None,
        surname2: str | None = None,
        given_name2: str | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
        parish_id: str | None = None,
        exact: bool = False,
        limit: int = 25,
        offset: int = 0,
    ) -> GenetekaSearchResult:
        """Search Geneteka for vital records (births / marriages / deaths).

        Notes:
        - `region` is a Geneteka region code from `geneteka_list_regions`
          (e.g. `05ld` for Łódzkie). The upstream search is region-scoped;
          to cover the whole country you must call once per region.
        - `surname` is required by the upstream API; given-name or place alone
          yields an empty response.
        - `surname2` / `given_name2` are the secondary parties:
            * for marriages, the bride (groom is the primary).
            * for births/deaths, the mother's maiden name.
        - `exact` disables substring matching on surnames.
        - `limit` is capped at 50 (Geneteka's max page size). Use `offset`
          to paginate across the full `total`.
        - Results are research candidates, not verified facts. Cross-check
          against Heredis (`heredis_search_persons`) before relying on them.
        """
        rt: RecordType = record_type
        regions = get_regions(client)
        if region not in regions:
            raise ValueError(
                f"Unknown region {region!r}. Call geneteka_list_regions for valid codes."
            )

        length = max(1, min(int(limit), 50))
        start = max(0, int(offset))

        payload = client.search(
            record_type=rt,
            region_code=region,
            surname=surname,
            surname2=surname2,
            given_name=given_name,
            given_name2=given_name2,
            from_year=from_year,
            to_year=to_year,
            place=place,
            parish_id=parish_id,
            exact=exact,
            start=start,
            length=length,
        )
        items: list[GenetekaRecord] = parse_rows(payload.get("data") or [], rt, region)
        return GenetekaSearchResult(
            record_type=rt,
            region_code=region,
            region_name=regions.get(region),
            total=parse_total(payload),
            limit=length,
            offset=start,
            items=items,
        )

    @mcp.tool
    def geneteka_check_surname(
        surname: str,
        from_year: int | None = None,
        to_year: int | None = None,
        exact: bool = False,
        record_type: Literal["birth", "marriage", "death"] = "birth",
    ) -> dict[str, int]:
        """Cheap surname-occurrence sweep: total `record_type` records per region.

        Issues one search per region (rate-limited) and reports the per-region
        `total` only — no rows are fetched. Useful as a first step to decide
        which region to drill into. Defaults to births because they're the
        densest record type.
        """
        rt: RecordType = record_type
        out: dict[str, int] = {}
        for code in get_regions(client):
            payload = client.search(
                record_type=rt,
                region_code=code,
                surname=surname,
                from_year=from_year,
                to_year=to_year,
                exact=exact,
                start=0,
                length=1,
            )
            out[code] = parse_total(payload)
        return out

    return client
