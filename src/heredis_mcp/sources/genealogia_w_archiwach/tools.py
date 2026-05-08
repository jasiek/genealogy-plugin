"""Register Genealogia w Archiwach research tools on a FastMCP server."""

from __future__ import annotations

from fastmcp import FastMCP

from heredis_mcp.sources.genealogia_w_archiwach.client import (
    GenealogiaWArchiwachClient,
    GenealogiaWArchiwachConfig,
)
from heredis_mcp.sources.genealogia_w_archiwach.models import (
    ActType,
    GenealogiaWArchiwachSearchResult,
    PersonRole,
    SearchScope,
)
from heredis_mcp.sources.genealogia_w_archiwach.parser import (
    extract_urls,
    image_urls,
    parse_records,
)


def register(
    mcp: FastMCP, config: GenealogiaWArchiwachConfig | None = None
) -> GenealogiaWArchiwachClient:
    """Register all `genealogia_w_archiwach_*` tools."""
    client = GenealogiaWArchiwachClient(config)

    @mcp.tool
    def genealogia_w_archiwach_search_person(
        query: str | None = None,
        given_name: str | None = None,
        surname: str | None = None,
        act_type: ActType | None = None,
        role: PersonRole | None = None,
        scope: SearchScope = "all",
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
    ) -> GenealogiaWArchiwachSearchResult:
        """Search Genealogia w Archiwach for person/document candidates.

        This is a live research source backed by the public Vaadin app at
        genealogiawarchiwach.pl. Results are candidates, not verified facts.
        Returned `image_urls` are scan/tile/IIIF-looking URLs found in the
        result payload and should be preserved when citing documents.
        """
        messages = client.search_person(
            query=query,
            given_name=given_name,
            surname=surname,
            act_type=act_type,
            role=role,
            scope=scope,
            from_year=from_year,
            to_year=to_year,
            place=place,
        )
        records = parse_records(messages, base_url=client.config.base_url)
        urls = extract_urls(messages, base_url=client.config.base_url)
        return GenealogiaWArchiwachSearchResult(
            query=query,
            given_name=given_name,
            surname=surname,
            scope=scope,
            total=len(records) if records else None,
            items=records,
            image_urls=image_urls(urls),
            urls=urls,
            warning=_warning(messages),
        )

    return client


def _warning(messages: list[dict]) -> str | None:
    for message in messages:
        app_error = (message.get("meta") or {}).get("appError") or {}
        if app_error:
            caption = app_error.get("caption") or "Genealogia w Archiwach error"
            details = app_error.get("message") or app_error.get("details")
            return f"{caption}: {details}" if details else str(caption)
    return None
