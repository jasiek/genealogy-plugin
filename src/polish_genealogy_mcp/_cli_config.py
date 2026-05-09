"""Shared CLI/env config plumbing.

Configuration can come from three sources, with this precedence:

    1. command-line flags        (highest)
    2. environment variables
    3. built-in defaults         (lowest)

Claude Desktop / Claude Code provide config to the server by setting
environment variables in the MCP server entry (see `manifest.json` and
the README), so "Claude config" maps onto layer 2.

This module exposes:

  - `add_config_arguments(parser)`   — register every config flag
  - `apply_cli_overrides(args)`      — copy CLI flags into os.environ so
    each source's existing `Config.from_env()` keeps working unchanged

Adding a new knob is two edits: register the flag here and read the env
var in the source's `Config.from_env()`.
"""

from __future__ import annotations

import argparse
import os

# (cli_dest, env_var, help_text)
_ENV_FLAGS: tuple[tuple[str, str, str], ...] = (
    (
        "heredis_db",
        "HEREDIS_DB",
        "Path to a .heredis SQLite file. Heredis tools register only when set.",
    ),
    (
        "gedcom_path",
        "GEDCOM_PATH",
        "Path to a GEDCOM file. GEDCOM tools register only when set.",
    ),
    (
        "geneteka_min_interval",
        "GENETEKA_MIN_INTERVAL",
        "Seconds between Geneteka requests (default 5).",
    ),
    ("geneteka_user_agent", "GENETEKA_USER_AGENT", "Override the User-Agent sent to Geneteka."),
    (
        "genealogia_w_archiwach_min_interval",
        "GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL",
        "Seconds between Genealogia w Archiwach requests (default 5).",
    ),
    (
        "genealogia_w_archiwach_user_agent",
        "GENEALOGIA_W_ARCHIWACH_USER_AGENT",
        "Override the User-Agent sent to Genealogia w Archiwach.",
    ),
    (
        "genbaza_min_interval",
        "GENBAZA_MIN_INTERVAL",
        "Seconds between genbaza requests (default 5).",
    ),
    ("genbaza_user_agent", "GENBAZA_USER_AGENT", "Override the User-Agent sent to genbaza."),
    (
        "lubgens_min_interval",
        "LUBGENS_MIN_INTERVAL",
        "Seconds between Lubgens requests (default 5).",
    ),
    ("lubgens_user_agent", "LUBGENS_USER_AGENT", "Override the User-Agent sent to Lubgens."),
    ("genpod_min_interval", "GENPOD_MIN_INTERVAL", "Seconds between GenPod requests (default 5)."),
    ("genpod_user_agent", "GENPOD_USER_AGENT", "Override the User-Agent sent to GenPod."),
    ("genpod_username", "GENPOD_USERNAME", "GenPod username (required to enable genpod_* tools)."),
    ("genpod_password", "GENPOD_PASSWORD", "GenPod password (required to enable genpod_* tools)."),
)

# (cli_dest, default_enabled)
_DISABLE_FLAGS: tuple[tuple[str, str], ...] = (
    ("no_geneteka", "Disable the Geneteka research source."),
    ("no_genealogia_w_archiwach", "Disable the Genealogia w Archiwach research source."),
    ("no_genbaza", "Disable the genbaza-family research source."),
    ("no_lubgens", "Disable the Lubgens research source."),
    ("no_genpod", "Disable the GenPod research source."),
)


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Register the shared config flags on `parser`."""
    for dest, env_var, help_text in _ENV_FLAGS:
        flag = "--" + dest.replace("_", "-")
        parser.add_argument(
            flag,
            default=None,
            help=f"{help_text} Env: ${env_var}.",
        )
    for dest, help_text in _DISABLE_FLAGS:
        flag = "--" + dest.replace("_", "-")
        parser.add_argument(flag, action="store_true", help=help_text)


def apply_cli_overrides(args: argparse.Namespace) -> None:
    """Copy any CLI flag values into `os.environ` so source `from_env()` sees them.

    CLI takes precedence over a pre-existing env var. Unset flags leave the
    environment alone.
    """
    for dest, env_var, _ in _ENV_FLAGS:
        value = getattr(args, dest, None)
        if value is not None:
            os.environ[env_var] = str(value)


def enabled_sources(args: argparse.Namespace) -> dict[str, bool]:
    """Map of `enable_<source>` flags ready to splat into `build_server`."""
    return {
        "enable_geneteka": not args.no_geneteka,
        "enable_genealogia_w_archiwach": not args.no_genealogia_w_archiwach,
        "enable_genbaza": not args.no_genbaza,
        "enable_lubgens": not args.no_lubgens,
        "enable_genpod": not args.no_genpod,
    }
