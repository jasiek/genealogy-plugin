"""Register genbaza research tools on a FastMCP server.

The genbaza family of sites (swietogen, polishgenealogy, warmia, kurpie,
pomerania) publish indexed vital records via near-identical PHP
frontends. This source is the *research* tier: candidate matches that
the user evaluates before committing anything to Heredis. Tool names are
prefixed ``genbaza_``.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from genealogy_mcp.sources.genbaza.client import GenbazaClient, GenbazaConfig
from genealogy_mcp.sources.genbaza.models import (
    GenbazaResourceList,
    GenbazaSearchResult,
    GenbazaSite,
)


def register(mcp: FastMCP, config: GenbazaConfig | None = None) -> GenbazaClient:
    """Register all `genbaza_*` tools. Returns the client so the caller can close it."""
    client = GenbazaClient(config)

    @mcp.tool
    def genbaza_list_sites() -> list[GenbazaSite]:
        """List the genbaza-family sites this server can query.

        Each entry's ``code`` is the value to pass as ``site`` to the
        other ``genbaza_*`` tools. The five sites cover different
        regions:

        - ``swietogen`` — Świętokrzyskie indexes (5.3M+ records)
        - ``warmia`` — Warmia / Mazury
        - ``pomerania`` — Pomerania (Szczecin-area Archives)
        - ``polishgenealogy`` — general Polish indexes
        - ``kurpie`` — Kurpie / Mazowsze (APW Pułtusk)
        """
        return [GenbazaSite(code=k, base_url=v) for k, v in client.list_sites().items()]

    @mcp.tool
    def genbaza_search(
        site: str,
        record_type: Literal["birth", "marriage", "death"] = "birth",
        surname: str | None = None,
        given_name: str | None = None,
        father: str | None = None,
        mother: str | None = None,
        mother_surname: str | None = None,
        spouse: str | None = None,
        spouse_surname: str | None = None,
        place: str | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        other: str | None = None,
        parish_filter: str | None = None,
        page: int = 1,
        exact_surname: bool = False,
        exact_given_name: bool = False,
        exact_place: bool = False,
    ) -> GenbazaSearchResult:
        """Search a genbaza index site for indexed vital records.

        - ``site`` is one of the codes returned by ``genbaza_list_sites``.
        - ``record_type`` only matters on the variant-A sites
          (``swietogen``, ``warmia``, ``pomerania``). The other two
          (``polishgenealogy``, ``kurpie``) ignore it and return a
          combined table; in that case the response's ``record_type``
          is ``null`` and ``counts`` carries a single ``"total"`` key.
        - ``from_year`` / ``to_year``, ``spouse*``, and ``parish_filter``
          are silently dropped on variant-B sites.
        - When the corresponding ``exact_*`` flag is False the upstream
          uses a Soundex matcher; when True it requires a literal match.
        - Each result row carries ``scan_url`` when the index entry
          links to a digitised image on ``metryki.genbaza.pl``. Note:
          viewing those scans typically requires a free GenBaza account.
          ``archive_ref`` always carries the physical archive shelfmark
          when the indexer recorded one (e.g. ``AP Kielce, 21/231/0``).
        - Results are research candidates, not verified facts.
          Cross-check against Heredis (``heredis_search_persons``)
          before relying on them.
        """
        return client.search(
            site,
            record_type=record_type,
            surname=surname,
            given_name=given_name,
            father=father,
            mother=mother,
            mother_surname=mother_surname,
            spouse=spouse,
            spouse_surname=spouse_surname,
            place=place,
            from_year=from_year,
            to_year=to_year,
            other=other,
            parish_filter=parish_filter,
            page=page,
            exact_surname=exact_surname,
            exact_given_name=exact_given_name,
            exact_place=exact_place,
        )

    @mcp.tool
    def genbaza_list_resources(site: str) -> GenbazaResourceList:
        """List the parishes / localities indexed on a given genbaza site.

        Returns each parish along with the year ranges currently indexed
        for births, marriages, and deaths. Pass a ``parish`` string back
        as ``parish_filter`` in ``genbaza_search`` to constrain results.
        """
        return client.list_resources(site)

    return client
