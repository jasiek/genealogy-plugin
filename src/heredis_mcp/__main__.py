"""Entry point for the genealogy MCP server.

Usage:
    heredis-mcp                                # live research sources only
    heredis-mcp --heredis-db path/to/file.heredis
    HEREDIS_DB=path/to/file heredis-mcp        # heredis + live research sources

Environment overrides:
    HEREDIS_DB                — default --heredis-db
    GENETEKA_MIN_INTERVAL     — seconds between Geneteka requests (default 5)
    GENETEKA_USER_AGENT       — override the outgoing User-Agent
    GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL
                              — seconds between Genealogia w Archiwach
                                requests (default 5)
    GENEALOGIA_W_ARCHIWACH_USER_AGENT
                              — override the outgoing User-Agent
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from heredis_mcp.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="heredis-mcp")
    parser.add_argument(
        "--heredis-db",
        default=os.environ.get("HEREDIS_DB"),
        help=(
            "Path to a .heredis SQLite file. If omitted, only live research "
            "source tools register."
        ),
    )
    parser.add_argument(
        "--no-geneteka",
        action="store_true",
        help="Disable the geneteka research source.",
    )
    parser.add_argument(
        "--no-genealogia-w-archiwach",
        action="store_true",
        help="Disable the Genealogia w Archiwach research source.",
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default=None,
        help=argparse.SUPPRESS,  # legacy positional, kept for compatibility
    )
    args = parser.parse_args()

    heredis_db = args.heredis_db or args.db_path
    enable_geneteka = not args.no_geneteka
    enable_genealogia_w_archiwach = not args.no_genealogia_w_archiwach

    if not heredis_db and not enable_geneteka and not enable_genealogia_w_archiwach:
        parser.error("Nothing to do: pass --heredis-db or enable at least one research source.")

    server = build_server(
        heredis_db=Path(heredis_db) if heredis_db else None,
        enable_geneteka=enable_geneteka,
        enable_genealogia_w_archiwach=enable_genealogia_w_archiwach,
    )
    server.run()


if __name__ == "__main__":
    sys.exit(main())
