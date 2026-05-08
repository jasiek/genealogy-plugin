"""Smoke tests that the FastMCP server constructs and exposes the expected tools."""

from __future__ import annotations

import asyncio

import pytest

from heredis_mcp.server import build_server

EXPECTED_TOOLS = {
    "search_persons",
    "get_person",
    "get_family",
    "search_events",
    "get_event",
    "search_places",
    "search_sources",
    "get_source",
}


def test_build_server_registers_all_tools(db_path):
    server = build_server(db_path)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS.issubset(names)


def test_build_server_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_server(tmp_path / "no-such-file.heredis")
