"""Smoke tests that the FastMCP server constructs and exposes the expected tools."""

from __future__ import annotations

import asyncio

import pytest

from genealogy_mcp.server import build_server

HEREDIS_TOOLS = {
    "heredis_search_persons",
    "heredis_get_person",
    "heredis_get_family",
    "heredis_search_events",
    "heredis_get_event",
    "heredis_search_places",
    "heredis_search_sources",
    "heredis_get_source",
}

GENETEKA_TOOLS = {
    "geneteka_list_regions",
    "geneteka_search",
    "geneteka_check_surname",
}

GENEALOGIA_W_ARCHIWACH_TOOLS = {
    "genealogia_w_archiwach_search_person",
}

GENPOD_TOOLS = {
    "genpod_search_vital_records",
    "genpod_list_parishes",
    "genpod_get_parish_year_imports",
}

GENBAZA_TOOLS = {
    "genbaza_list_sites",
    "genbaza_search",
    "genbaza_list_resources",
}

LUBGENS_TOOLS = {
    "lubgens_search",
}

BASIA_TOOLS = {
    "basia_search",
}


def _tool_names(server) -> set[str]:
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_build_server_registers_all_tools(db_path):
    server = build_server(heredis_db=db_path)
    names = _tool_names(server)
    assert HEREDIS_TOOLS.issubset(names)
    assert GENETEKA_TOOLS.issubset(names)
    assert GENEALOGIA_W_ARCHIWACH_TOOLS.issubset(names)
    assert GENPOD_TOOLS.issubset(names)
    assert GENBAZA_TOOLS.issubset(names)
    assert LUBGENS_TOOLS.issubset(names)
    assert BASIA_TOOLS.issubset(names)


def test_build_server_geneteka_only():
    server = build_server(heredis_db=None, enable_geneteka=True)
    names = _tool_names(server)
    assert GENETEKA_TOOLS.issubset(names)
    assert names.isdisjoint(HEREDIS_TOOLS)
    assert GENEALOGIA_W_ARCHIWACH_TOOLS.issubset(names)
    assert GENPOD_TOOLS.issubset(names)


def test_build_server_heredis_only(db_path):
    server = build_server(
        heredis_db=db_path,
        enable_geneteka=False,
        enable_genealogia_w_archiwach=False,
        enable_genpod=False,
        enable_genbaza=False,
    )
    names = _tool_names(server)
    assert HEREDIS_TOOLS.issubset(names)
    assert names.isdisjoint(GENETEKA_TOOLS)
    assert names.isdisjoint(GENEALOGIA_W_ARCHIWACH_TOOLS)
    assert names.isdisjoint(GENPOD_TOOLS)
    assert names.isdisjoint(GENBAZA_TOOLS)


def test_build_server_genealogia_w_archiwach_only():
    server = build_server(
        heredis_db=None,
        enable_geneteka=False,
        enable_genealogia_w_archiwach=True,
        enable_genpod=False,
        enable_genbaza=False,
    )
    names = _tool_names(server)
    assert GENEALOGIA_W_ARCHIWACH_TOOLS.issubset(names)
    assert names.isdisjoint(HEREDIS_TOOLS)
    assert names.isdisjoint(GENETEKA_TOOLS)
    assert names.isdisjoint(GENPOD_TOOLS)
    assert names.isdisjoint(GENBAZA_TOOLS)


def test_build_server_genpod_only():
    server = build_server(
        heredis_db=None,
        enable_geneteka=False,
        enable_genealogia_w_archiwach=False,
        enable_genpod=True,
        enable_genbaza=False,
    )
    names = _tool_names(server)
    assert GENPOD_TOOLS.issubset(names)
    assert names.isdisjoint(HEREDIS_TOOLS)
    assert names.isdisjoint(GENETEKA_TOOLS)
    assert names.isdisjoint(GENEALOGIA_W_ARCHIWACH_TOOLS)
    assert names.isdisjoint(GENBAZA_TOOLS)


def test_build_server_genbaza_only():
    server = build_server(
        heredis_db=None,
        enable_geneteka=False,
        enable_genealogia_w_archiwach=False,
        enable_genpod=False,
        enable_genbaza=True,
    )
    names = _tool_names(server)
    assert GENBAZA_TOOLS.issubset(names)
    assert names.isdisjoint(HEREDIS_TOOLS)
    assert names.isdisjoint(GENETEKA_TOOLS)
    assert names.isdisjoint(GENEALOGIA_W_ARCHIWACH_TOOLS)
    assert names.isdisjoint(GENPOD_TOOLS)


def test_build_server_rejects_no_sources():
    with pytest.raises(ValueError):
        build_server(
            heredis_db=None,
            enable_geneteka=False,
            enable_genealogia_w_archiwach=False,
            enable_genpod=False,
            enable_genbaza=False,
            enable_lubgens=False,
            enable_basia=False,
        )


def test_build_server_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_server(heredis_db=tmp_path / "no-such-file.heredis")
