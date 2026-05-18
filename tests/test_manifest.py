"""Assert that manifest.json stays in sync with the config registry.

`_cli_config.CONFIG_ENTRIES` is the source of truth: every entry marked
`expose_in_manifest=True` must appear in both the `server.mcp_config.env`
mapping and the `user_config` block of manifest.json. Conversely, the
manifest must not reference any field the registry doesn't declare.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genealogy_mcp._cli_config import CONFIG_ENTRIES


@pytest.fixture(scope="module")
def manifest() -> dict:
    path = Path(__file__).resolve().parent.parent / "manifest.json"
    return json.loads(path.read_text())


def _exposed():
    return [e for e in CONFIG_ENTRIES if e.expose_in_manifest]


def test_user_config_field_per_exposed_entry(manifest: dict) -> None:
    user_config = manifest["user_config"]
    for entry in _exposed():
        assert (
            entry.dest in user_config
        ), f"manifest.json user_config is missing an entry for {entry.dest!r}"
        field = user_config[entry.dest]
        assert field["type"] == entry.manifest_type
        assert field["title"] == entry.manifest_title
        assert field["description"] == entry.manifest_description
        assert field.get("required", False) == entry.manifest_required
        if entry.manifest_default is not None:
            assert field.get("default") == entry.manifest_default
        if entry.sensitive:
            assert field.get("sensitive") is True


def test_env_block_wires_every_exposed_entry(manifest: dict) -> None:
    env = manifest["server"]["mcp_config"]["env"]
    for entry in _exposed():
        expected = "${user_config." + entry.dest + "}"
        assert env.get(entry.env_var) == expected, (
            f"manifest.json server.mcp_config.env is missing " f"{entry.env_var}={expected}"
        )


def test_no_orphan_user_config_fields(manifest: dict) -> None:
    declared = {e.dest for e in _exposed()}
    for name in manifest["user_config"]:
        assert name in declared, (
            f"manifest.json user_config declares {name!r} which is not in "
            f"_cli_config.CONFIG_ENTRIES (or is missing expose_in_manifest=True)"
        )


def test_no_orphan_env_keys(manifest: dict) -> None:
    declared = {e.env_var for e in _exposed()}
    for name in manifest["server"]["mcp_config"]["env"]:
        assert name in declared, (
            f"manifest.json server.mcp_config.env declares {name!r} which is "
            f"not in _cli_config.CONFIG_ENTRIES (or is missing expose_in_manifest=True)"
        )
