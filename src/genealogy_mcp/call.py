"""CLI for invoking individual MCP tools without an MCP client.

Configuration is read with the same precedence as the server itself:
CLI flag > environment variable > built-in default. Run with `--help`
for the full list of config flags.

Examples:

    # list every registered tool
    genealogy-mcp-call --list

    # show a tool's input JSON Schema
    genealogy-mcp-call --tool heredis_search_persons --schema

    # invoke with key=value args (each value is JSON-parsed; falls back to str)
    genealogy-mcp-call --heredis-db Szumiec.heredis \\
        --tool heredis_search_persons surname=Szumiec limit=5

    # or pass the full argument object as JSON
    genealogy-mcp-call --tool geneteka_search \\
        --json '{"region":"06mp","surname":"Szumiec"}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from genealogy_mcp._cli_config import (
    add_config_arguments,
    apply_cli_overrides,
    enabled_sources,
)
from genealogy_mcp.server import build_server


def _parse_kv(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw in pairs:
        if "=" not in raw:
            raise SystemExit(f"bad arg {raw!r}: expected key=value")
        key, value = raw.split("=", 1)
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def _print_tool_summary(tools: list[Any]) -> None:
    width = max((len(t.name) for t in tools), default=0)
    for t in sorted(tools, key=lambda x: x.name):
        first_line = (t.description or "").strip().splitlines()
        head = first_line[0] if first_line else ""
        print(f"{t.name:<{width}}  {head}")


def _serialize_result(result: Any) -> Any:
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "content"):
        out = []
        for c in result.content:
            text = getattr(c, "text", None)
            if text is not None:
                try:
                    out.append(json.loads(text))
                except json.JSONDecodeError:
                    out.append(text)
            else:
                out.append(repr(c))
        return out
    return result


async def _run(args: argparse.Namespace) -> int:
    heredis_db = os.environ.get("HEREDIS_DB")
    gedcom_path = os.environ.get("GEDCOM_PATH")
    server = build_server(
        heredis_db=Path(heredis_db) if heredis_db else None,
        gedcom_path=Path(gedcom_path) if gedcom_path else None,
        **enabled_sources(args),
    )
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}

    if args.list:
        _print_tool_summary(tools)
        return 0

    if not args.tool:
        print("error: --tool is required (or use --list)", file=sys.stderr)
        return 2

    tool = by_name.get(args.tool)
    if tool is None:
        print(f"error: unknown tool {args.tool!r}", file=sys.stderr)
        print("available tools:", file=sys.stderr)
        _print_tool_summary(tools)
        return 2

    if args.schema:
        print(json.dumps(tool.parameters, indent=2))
        return 0

    if args.json:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as exc:
            print(f"error: --json is not valid JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(payload, dict):
            print("error: --json must be a JSON object", file=sys.stderr)
            return 2
    else:
        payload = {}

    payload.update(_parse_kv(args.kv))

    result = await server.call_tool(args.tool, payload)
    print(json.dumps(_serialize_result(result), indent=2, ensure_ascii=False, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="genealogy-mcp-call",
        description=(
            "Invoke an individual tool registered with the MCP server. "
            "Config precedence: CLI flag > environment variable > default."
        ),
    )
    add_config_arguments(parser)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="List registered tools and exit.")
    mode.add_argument("--tool", help="Name of the tool to invoke or inspect.")
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the selected tool's input JSON Schema and exit.",
    )
    parser.add_argument(
        "--json",
        help="Full argument object as a JSON string. Merged with key=value pairs.",
    )
    parser.add_argument(
        "kv",
        nargs="*",
        help="Tool arguments as key=value (values are JSON-parsed when possible).",
    )
    args = parser.parse_args()

    if not args.list and not args.tool:
        parser.error("either --list or --tool is required")

    apply_cli_overrides(args)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
