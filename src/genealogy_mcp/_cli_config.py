"""Shared CLI/env config plumbing.

Configuration can come from three sources, with this precedence:

    1. command-line flags        (highest)
    2. environment variables
    3. built-in defaults         (lowest)

MCP clients (Claude Code, etc.) provide config to the server by setting
environment variables in the MCP server entry, so "client config" maps onto
layer 2.

The single source of truth is `CONFIG_ENTRIES` below: each entry declares
the CLI flag, env var, and help text. Two consumers read this registry:

  - `add_config_arguments(parser)` — register every CLI flag
  - `apply_cli_overrides(args)`    — copy CLI values into os.environ so
    each source's existing `Config.from_env()` keeps working unchanged

Adding a new knob is one edit: add a `ConfigEntry` here.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigEntry:
    """One configuration knob, surfaced as a CLI flag and an env var."""

    dest: str
    env_var: str
    help: str

    @property
    def cli_flag(self) -> str:
        return "--" + self.dest.replace("_", "-")


CONFIG_ENTRIES: tuple[ConfigEntry, ...] = (
    ConfigEntry(
        dest="heredis_db",
        env_var="HEREDIS_DB",
        help=(
            "Path to a .heredis SQLite file. Overrides cwd auto-discovery. "
            "Heredis tools register only when a file is set or discovered."
        ),
    ),
    ConfigEntry(
        dest="gedcom_path",
        env_var="GEDCOM_PATH",
        help=(
            "Path to a GEDCOM file. Overrides cwd auto-discovery. "
            "GEDCOM tools register only when a file is set or discovered."
        ),
    ),
    ConfigEntry(
        dest="geneteka_min_interval",
        env_var="GENETEKA_MIN_INTERVAL",
        help="Seconds between Geneteka requests (default 5).",
    ),
    ConfigEntry(
        dest="geneteka_user_agent",
        env_var="GENETEKA_USER_AGENT",
        help="Override the User-Agent sent to Geneteka.",
    ),
    ConfigEntry(
        dest="genealogia_w_archiwach_min_interval",
        env_var="GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL",
        help="Seconds between Genealogia w Archiwach requests (default 5).",
    ),
    ConfigEntry(
        dest="genealogia_w_archiwach_user_agent",
        env_var="GENEALOGIA_W_ARCHIWACH_USER_AGENT",
        help="Override the User-Agent sent to Genealogia w Archiwach.",
    ),
    ConfigEntry(
        dest="genbaza_min_interval",
        env_var="GENBAZA_MIN_INTERVAL",
        help="Seconds between genbaza requests (default 5).",
    ),
    ConfigEntry(
        dest="genbaza_user_agent",
        env_var="GENBAZA_USER_AGENT",
        help="Override the User-Agent sent to genbaza.",
    ),
    ConfigEntry(
        dest="lubgens_min_interval",
        env_var="LUBGENS_MIN_INTERVAL",
        help="Seconds between Lubgens requests (default 5).",
    ),
    ConfigEntry(
        dest="lubgens_user_agent",
        env_var="LUBGENS_USER_AGENT",
        help="Override the User-Agent sent to Lubgens.",
    ),
    ConfigEntry(
        dest="genpod_min_interval",
        env_var="GENPOD_MIN_INTERVAL",
        help="Seconds between GenPod requests (default 5).",
    ),
    ConfigEntry(
        dest="genpod_user_agent",
        env_var="GENPOD_USER_AGENT",
        help="Override the User-Agent sent to GenPod.",
    ),
    ConfigEntry(
        dest="genpod_username",
        env_var="GENPOD_USERNAME",
        help="GenPod username (required to enable genpod_* tools).",
    ),
    ConfigEntry(
        dest="genpod_password",
        env_var="GENPOD_PASSWORD",
        help="GenPod password (required to enable genpod_* tools).",
    ),
)

# (cli_dest, help_text) — boolean toggles, default False (i.e. source is enabled).
_DISABLE_FLAGS: tuple[tuple[str, str], ...] = (
    ("no_geneteka", "Disable the Geneteka research source."),
    ("no_genealogia_w_archiwach", "Disable the Genealogia w Archiwach research source."),
    ("no_genbaza", "Disable the genbaza-family research source."),
    ("no_lubgens", "Disable the Lubgens research source."),
    ("no_genpod", "Disable the GenPod research source."),
)


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Register the shared config flags on `parser`."""
    for entry in CONFIG_ENTRIES:
        parser.add_argument(
            entry.cli_flag,
            default=None,
            help=f"{entry.help} Env: ${entry.env_var}.",
        )
    for dest, help_text in _DISABLE_FLAGS:
        flag = "--" + dest.replace("_", "-")
        parser.add_argument(flag, action="store_true", help=help_text)


def apply_cli_overrides(args: argparse.Namespace) -> None:
    """Copy any CLI flag values into `os.environ` so source `from_env()` sees them.

    CLI takes precedence over a pre-existing env var. Unset flags leave the
    environment alone.
    """
    for entry in CONFIG_ENTRIES:
        value = getattr(args, entry.dest, None)
        if value is not None:
            os.environ[entry.env_var] = str(value)


def enabled_sources(args: argparse.Namespace) -> dict[str, bool]:
    """Map of `enable_<source>` flags ready to splat into `build_server`."""
    return {
        "enable_geneteka": not args.no_geneteka,
        "enable_genealogia_w_archiwach": not args.no_genealogia_w_archiwach,
        "enable_genbaza": not args.no_genbaza,
        "enable_lubgens": not args.no_lubgens,
        "enable_genpod": not args.no_genpod,
    }
