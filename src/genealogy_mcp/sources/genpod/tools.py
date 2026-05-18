"""Register authenticated GenPod research tools on a FastMCP server."""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from genealogy_mcp.sources.genpod.client import GenpodClient, GenpodConfig
from genealogy_mcp.sources.genpod.models import (
    GenpodParishCoverageResult,
    GenpodParishSummary,
    GenpodParishYearImportsResult,
    GenpodRecordType,
    GenpodSearchResult,
)


def register(mcp: FastMCP, config: GenpodConfig | None = None) -> GenpodClient:
    """Register all `genpod_*` tools."""
    client = GenpodClient(config)

    @mcp.tool
    def genpod_search_vital_records(
        last_name: str | None = None,
        first_name: str | None = None,
        last_name_exact: bool = False,
        second_person_last_name: str | None = None,
        second_person_last_name_exact: bool = False,
        year_from: int | None = None,
        year_to: int | None = None,
        parish_id: int | None = None,
        wyznanie: str | None = None,
        record_types: list[Literal["birth", "marriage", "death"]] | None = None,
        limit: int = 25,
        page: int = 1,
    ) -> GenpodSearchResult:
        """Search authenticated GenPod vital-record indexes.

        GenPod is a research source: results are candidates, not verified
        facts. Credentials are read from `GENPOD_USERNAME` and
        `GENPOD_PASSWORD` by the server process. `second_person_last_name`
        means the spouse surname for marriages and the mother's surname for
        births/deaths. `parish_id` is the Projekt Podlasie catalog parish id.
        """
        requested: list[GenpodRecordType] | None = (
            [record_type for record_type in record_types] if record_types else None
        )
        data = client.search_vital_records(
            last_name=last_name,
            first_name=first_name,
            last_name_exact=last_name_exact,
            second_person_last_name=second_person_last_name,
            second_person_last_name_exact=second_person_last_name_exact,
            year_from=year_from,
            year_to=year_to,
            parish_id=parish_id,
            wyznanie=wyznanie,
            record_types=requested,
            limit=limit,
            page=page,
        )
        return _search_result(data)

    @mcp.tool
    def genpod_list_parishes() -> GenpodParishCoverageResult:
        """List GenPod parish coverage and recent update histogram."""
        data = client.list_parishes()
        return GenpodParishCoverageResult(
            parishes=[
                GenpodParishSummary.model_validate(item)
                for item in data.get("parafieIndexingSummary") or []
            ],
            updateHistogram=(data.get("parafieUpdateHistogram") or {}).get("buckets") or [],
        )

    @mcp.tool
    def genpod_get_parish_year_imports(parish_name: str) -> GenpodParishYearImportsResult:
        """Get recently imported years for one GenPod parish name."""
        data = client.get_parish_year_imports(parish_name)
        return GenpodParishYearImportsResult.model_validate(data["parafiaYearImports"])

    return client


def _search_result(data: dict) -> GenpodSearchResult:
    keys = {
        "birth": "urodzenia",
        "marriage": "malzenstwa",
        "death": "zgony",
    }
    total: dict[str, int | None] = {}
    items: dict[str, list[dict]] = {}
    warnings: dict[str, str | None] = {}
    for public_name, gql_name in keys.items():
        section = data.get(gql_name) or {}
        total[public_name] = section.get("totalResultCount")
        items[public_name] = section.get("results") or []
        warnings[public_name] = (
            "GenPod reports that a surname fragment was not provided."
            if section.get("didNotProvideLastNameFragment")
            else None
        )
    return GenpodSearchResult(total=total, items=items, warnings=warnings)
