"""Entry point for the genealogy MCP server.

Configuration can come from (in precedence order):

    1. command-line flags          — `--heredis-db`, `--geneteka-min-interval`, ...
    2. environment variables       — `HEREDIS_DB`, `GENETEKA_MIN_INTERVAL`, ...
    3. cwd auto-discovery          — first `*.heredis` / `*.ged` in the
                                     current working directory (sorted)
    4. built-in defaults

MCP clients (Claude Code, etc.) supply tunables (rate limits, GenPod creds)
via env vars from the MCP server entry; the verified-facts file (Heredis or
GEDCOM) is discovered from the project directory the server is launched in.

Examples:
    genealogy-mcp                                # live research sources only,
                                                 # or auto-detect a .heredis/.ged in cwd
    genealogy-mcp --heredis-db path/to/file.heredis
    HEREDIS_DB=path/to/file genealogy-mcp        # explicit override
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from genealogy_mcp._cli_config import (
    add_config_arguments,
    apply_cli_overrides,
    enabled_sources,
)
from genealogy_mcp.server import build_server


def _discover_in_cwd(pattern: str) -> str | None:
    """Return the first file matching `pattern` in the current working directory.

    Used to auto-activate the heredis and gedcom sources when the server is
    launched from a user project directory containing a single such file.
    Sorted lexicographically for determinism; explicit CLI / env values win.
    """
    matches = sorted(Path.cwd().glob(pattern))
    return str(matches[0]) if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="genealogy-mcp",
        description=(
            "Run the polish-genealogy MCP server. Config precedence: "
            "CLI flag > environment variable > cwd auto-discovery > default."
        ),
    )
    add_config_arguments(parser)
    parser.add_argument(
        "db_path",
        nargs="?",
        default=None,
        help=argparse.SUPPRESS,  # legacy positional, kept for compatibility
    )
    args = parser.parse_args()
    apply_cli_overrides(args)

    heredis_db = os.environ.get("HEREDIS_DB") or args.db_path or _discover_in_cwd("*.heredis")
    gedcom_path = os.environ.get("GEDCOM_PATH") or _discover_in_cwd("*.ged")
    sources = enabled_sources(args)

    if not heredis_db and not gedcom_path and not any(sources.values()):
        parser.error(
            "Nothing to do: pass --heredis-db, --gedcom-path, "
            "or enable at least one research source."
        )

    server = build_server(
        heredis_db=Path(heredis_db) if heredis_db else None,
        gedcom_path=Path(gedcom_path) if gedcom_path else None,
        **sources,
    )
    server.run()


if __name__ == "__main__":
    sys.exit(main())
