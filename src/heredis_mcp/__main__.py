"""Entry point: `python -m heredis_mcp <path-to-.heredis>` or `heredis-mcp <path>`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from heredis_mcp.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="heredis-mcp")
    parser.add_argument(
        "db_path",
        nargs="?",
        default=os.environ.get("HEREDIS_DB"),
        help="Path to a .heredis SQLite file (or set HEREDIS_DB).",
    )
    args = parser.parse_args()
    if not args.db_path:
        parser.error("db_path is required (or set HEREDIS_DB)")

    server = build_server(Path(args.db_path))
    server.run()


if __name__ == "__main__":
    sys.exit(main())
