"""Entry point for the genealogy MCP server.

Configuration can come from (in precedence order):

    1. command-line flags          — `--heredis-db`, `--geneteka-min-interval`, ...
    2. environment variables       — `HEREDIS_DB`, `GENETEKA_MIN_INTERVAL`, ...
    3. built-in defaults

Claude Desktop / Claude Code supply config by setting the env vars in the
MCP server entry (see `manifest.json` and the README), so "Claude config"
maps onto layer 2. Run with `--help` for the full list.

Examples:
    polish-genealogy-mcp                                # live research sources only
    polish-genealogy-mcp --heredis-db path/to/file.heredis
    HEREDIS_DB=path/to/file polish-genealogy-mcp        # heredis + live research sources
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from polish_genealogy_mcp._cli_config import (
    add_config_arguments,
    apply_cli_overrides,
    enabled_sources,
)
from polish_genealogy_mcp.server import build_server

_DXT_ENV_VARS = (
    "HEREDIS_DB",
    "GENETEKA_MIN_INTERVAL",
    "GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL",
    "GENBAZA_MIN_INTERVAL",
    "LUBGENS_MIN_INTERVAL",
    "GENPOD_MIN_INTERVAL",
    "GENPOD_USERNAME",
    "GENPOD_PASSWORD",
)


def _scrub_dxt_templates() -> None:
    """Drop env vars whose value is still an unsubstituted DXT template.

    When a Claude Desktop user leaves an optional user_config field blank, the
    DXT runtime passes the literal `${user_config.<name>}` through as the env
    var rather than an empty string. Treat that as unset.
    """
    for name in _DXT_ENV_VARS:
        value = os.environ.get(name)
        if value is not None and "${" in value:
            os.environ.pop(name, None)


def main() -> None:
    _scrub_dxt_templates()
    parser = argparse.ArgumentParser(
        prog="polish-genealogy-mcp",
        description=(
            "Run the polish-genealogy MCP server. Config precedence: "
            "CLI flag > environment variable > default."
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

    heredis_db = os.environ.get("HEREDIS_DB") or args.db_path
    sources = enabled_sources(args)

    if not heredis_db and not any(sources.values()):
        parser.error("Nothing to do: pass --heredis-db or enable at least one research source.")

    server = build_server(
        heredis_db=Path(heredis_db) if heredis_db else None,
        **sources,
    )
    server.run()


if __name__ == "__main__":
    sys.exit(main())
