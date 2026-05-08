"""FastMCP server multiplexing genealogy sources.

Currently registers three tool groups:

  - `heredis_*` — read-only access to the user's Heredis SQLite file. This
    is the *verified facts* tier: only data the user has researched and
    committed locally. Optional: skip if no `heredis_db` is provided.

  - `geneteka_*` — search Polish parish-record indexes at
    https://geneteka.genealodzy.pl. This is the *research* tier: candidate
    matches the agent should propose, never write back without user review.

  - `genealogia_w_archiwach_*` — live search of
    https://www.genealogiawarchiwach.pl for archival person/document
    candidates and scan links.

New sources should follow the same shape: a `sources/<name>/tools.py` with
a `register(mcp, ...)` function that adds prefixed tools.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from heredis_mcp.sources.genealogia_w_archiwach import (
    register as register_genealogia_w_archiwach,
)
from heredis_mcp.sources.genealogia_w_archiwach.client import (
    GenealogiaWArchiwachConfig,
)
from heredis_mcp.sources.geneteka import register as register_geneteka
from heredis_mcp.sources.geneteka.client import GenetekaConfig
from heredis_mcp.sources.heredis import register as register_heredis

INSTRUCTIONS = (
    "Genealogy MCP server. Two source tiers:\n"
    "  - heredis_*: the user's *verified facts* (their personal Heredis "
    "file). Treat as authoritative.\n"
    "  - geneteka_*: live search over Polish parish-record indexes — "
    "*research candidates only*. Do not propose changes to Heredis "
    "based on geneteka results without showing the candidates to the "
    "user first.\n"
    "  - genealogia_w_archiwach_*: live search over Genealogia w Archiwach "
    "for archival person/document candidates and scan/image URLs — "
    "*research candidates only*.\n"
    "Workflow: call heredis_search_persons / heredis_get_family for "
    "context, then geneteka_search or genealogia_w_archiwach_search_person "
    "to find candidate records, then present matches for the user to confirm."
)


def build_server(
    heredis_db: Path | str | None = None,
    geneteka_config: GenetekaConfig | None = None,
    genealogia_w_archiwach_config: GenealogiaWArchiwachConfig | None = None,
    enable_geneteka: bool = True,
    enable_genealogia_w_archiwach: bool = True,
) -> FastMCP:
    """Construct the unified FastMCP server.

    At least one source must be enabled. By default geneteka is on and
    heredis is enabled iff a path is provided.
    """
    mcp = FastMCP(name="heredis-mcp", instructions=INSTRUCTIONS)

    if heredis_db is not None:
        register_heredis(mcp, heredis_db)

    if enable_geneteka:
        register_geneteka(mcp, geneteka_config)

    if enable_genealogia_w_archiwach:
        register_genealogia_w_archiwach(mcp, genealogia_w_archiwach_config)

    if heredis_db is None and not enable_geneteka and not enable_genealogia_w_archiwach:
        raise ValueError(
            "build_server: at least one source must be enabled "
            "(provide heredis_db, set enable_geneteka=True, or set "
            "enable_genealogia_w_archiwach=True)"
        )

    return mcp
