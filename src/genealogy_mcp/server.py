"""FastMCP server multiplexing genealogy sources.

Currently registers these tool groups:

  - `heredis_*` — read-only access to the user's Heredis SQLite file. This
    is the *verified facts* tier: only data the user has researched and
    committed locally. Optional: skip if no `heredis_db` is provided.

  - `geneteka_*` — search Polish parish-record indexes at
    https://geneteka.genealodzy.pl. This is the *research* tier: candidate
    matches the agent should propose, never write back without user review.

  - `genealogia_w_archiwach_*` — live search of
    https://www.genealogiawarchiwach.pl for archival person/document
    candidates and scan links.

  - `genpod_*` — authenticated live search of
    https://genpod.projektpodlasie.pl for Projekt Podlasie index candidates.

  - `genbaza_*` — live search of the genbaza-family regional indexes
    (swietogen, polishgenealogy, warmia, kurpie, pomerania). Surfaces
    scan URLs on metryki.genbaza.pl when the indexed entry links to a
    digitised image.

New sources should follow the same shape: a `sources/<name>/tools.py` with
a `register(mcp, ...)` function that adds prefixed tools.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from genealogy_mcp.sources.basia import register as register_basia
from genealogy_mcp.sources.basia.client import BasiaConfig
from genealogy_mcp.sources.gedcom import register as register_gedcom
from genealogy_mcp.sources.genbaza import register as register_genbaza
from genealogy_mcp.sources.genbaza.client import GenbazaConfig
from genealogy_mcp.sources.genealogia_w_archiwach import (
    register as register_genealogia_w_archiwach,
)
from genealogy_mcp.sources.genealogia_w_archiwach.client import (
    GenealogiaWArchiwachConfig,
)
from genealogy_mcp.sources.genealogyindexer import register as register_genealogyindexer
from genealogy_mcp.sources.genealogyindexer.client import GenealogyIndexerConfig
from genealogy_mcp.sources.genpod import register as register_genpod
from genealogy_mcp.sources.genpod.client import GenpodConfig
from genealogy_mcp.sources.geneteka import register as register_geneteka
from genealogy_mcp.sources.geneteka.client import GenetekaConfig
from genealogy_mcp.sources.heredis import register as register_heredis
from genealogy_mcp.sources.lubgens import register as register_lubgens
from genealogy_mcp.sources.lubgens.client import LubgensConfig

INSTRUCTIONS = (
    "Genealogy MCP server. Two source tiers:\n"
    "  - heredis_*: the user's *verified facts* (their personal Heredis "
    "file). Treat as authoritative.\n"
    "  - gedcom_*: the user's *verified facts* loaded from a GEDCOM file. "
    "Same authoritative status as heredis_* — pick whichever source the "
    "user has configured.\n"
    "  - geneteka_*: live search over Polish parish-record indexes — "
    "*research candidates only*. Do not propose changes to Heredis "
    "based on geneteka results without showing the candidates to the "
    "user first.\n"
    "  - genealogia_w_archiwach_*: live search over Genealogia w Archiwach "
    "for archival person/document candidates and scan/image URLs — "
    "*research candidates only*.\n"
    "  - genpod_*: authenticated live search over Projekt Podlasie GenPod "
    "indexes — *research candidates only*. Requires GENPOD_USERNAME and "
    "GENPOD_PASSWORD in the server environment.\n"
    "  - genbaza_*: live search over the genbaza-family regional vital-record "
    "indexes (swietogen, polishgenealogy, warmia, kurpie, pomerania) — "
    "*research candidates only*. Returns scan URLs when the indexed record "
    "links to a digitised image (viewing the scan typically requires a free "
    "GenBaza account).\n"
    "  - lubgens_*: live search over the Lubelskie Korzenie regional index "
    "(https://regestry.lubgens.eu) of Lublin-area parish registers and USC "
    "records — *research candidates only*. Returns scan URLs (typically "
    "szukajwarchiwach.gov.pl or familysearch.org) when the indexed entry "
    "links to a digitised image, plus best-effort parent extraction.\n"
    "  - basia_*: live search over BaSIA (https://basia.famula.pl), the "
    "WTG-Gniazdo / PSNC index of Wielkopolska (Greater Poland) archival "
    "vital records — *research candidates only*. A slow fuzzy match over "
    "6.6M+ entries; narrow with given name / year / place / record type. "
    "Returns scan URLs and a stable permalink per hit.\n"
    "  - genealogyindexer_*: full-text OCR search over Genealogy Indexer "
    "(https://genealogyindexer.org) — digitised directories, yizkor "
    "(memorial) books, military lists, histories, and school sources from "
    "Central/Eastern Europe — *research candidates only*. Surfaces a "
    "context snippet (or directory row) and a scan URL per matching page; "
    "good for finding where a surname was *printed* rather than registered.\n"
    "Workflow: call heredis_search_persons / heredis_get_family for "
    "context, then geneteka_search, genealogia_w_archiwach_search_person, "
    "genpod_search_vital_records, genbaza_search, lubgens_search, "
    "basia_search, or genealogyindexer_search to find candidate records, "
    "then present matches for the user to confirm."
)


def build_server(
    heredis_db: Path | str | None = None,
    gedcom_path: Path | str | None = None,
    geneteka_config: GenetekaConfig | None = None,
    genealogia_w_archiwach_config: GenealogiaWArchiwachConfig | None = None,
    genpod_config: GenpodConfig | None = None,
    genbaza_config: GenbazaConfig | None = None,
    lubgens_config: LubgensConfig | None = None,
    basia_config: BasiaConfig | None = None,
    genealogyindexer_config: GenealogyIndexerConfig | None = None,
    enable_geneteka: bool = True,
    enable_genealogia_w_archiwach: bool = True,
    enable_genpod: bool = True,
    enable_genbaza: bool = True,
    enable_lubgens: bool = True,
    enable_basia: bool = True,
    enable_genealogyindexer: bool = True,
) -> FastMCP:
    """Construct the unified FastMCP server.

    At least one source must be enabled. By default geneteka is on and
    heredis is enabled iff a path is provided.
    """
    mcp = FastMCP(name="genealogy-mcp", instructions=INSTRUCTIONS)

    if heredis_db is not None:
        register_heredis(mcp, heredis_db)

    if gedcom_path is not None:
        register_gedcom(mcp, gedcom_path)

    if enable_geneteka:
        register_geneteka(mcp, geneteka_config)

    if enable_genealogia_w_archiwach:
        register_genealogia_w_archiwach(mcp, genealogia_w_archiwach_config)

    if enable_genpod:
        register_genpod(mcp, genpod_config)

    if enable_genbaza:
        register_genbaza(mcp, genbaza_config)

    if enable_lubgens:
        register_lubgens(mcp, lubgens_config)

    if enable_basia:
        register_basia(mcp, basia_config)

    if enable_genealogyindexer:
        register_genealogyindexer(mcp, genealogyindexer_config)

    if (
        heredis_db is None
        and gedcom_path is None
        and not enable_geneteka
        and not enable_genealogia_w_archiwach
        and not enable_genpod
        and not enable_genbaza
        and not enable_lubgens
        and not enable_basia
        and not enable_genealogyindexer
    ):
        raise ValueError(
            "build_server: at least one source must be enabled "
            "(provide heredis_db, gedcom_path, set enable_geneteka=True, "
            "enable_genealogia_w_archiwach=True, enable_genpod=True, "
            "enable_genbaza=True, enable_lubgens=True, enable_basia=True, "
            "or enable_genealogyindexer=True)"
        )

    return mcp
