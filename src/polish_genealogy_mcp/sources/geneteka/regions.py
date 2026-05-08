"""Region catalogue: live fetch with on-disk weekly cache.

Geneteka adds new regions every few years (e.g. the foreign-lands groupings
came later than the original 16 voivodeships). Hardcoding the table works
right now but rots quietly. So we fetch the surname-occurrence form page
(`?op=se`), scrape the region links, and cache the result on disk for a
week. On any failure we fall back to the static `REGIONS` dict in
`constants.py` so the tool never goes dark.

Cache layout: a single JSON file at
`$XDG_CACHE_HOME/polish-genealogy-mcp/geneteka_regions.json` (falling back to
`~/.cache/polish-genealogy-mcp/...`). Format:

    {
      "fetched_at_epoch": 1715164800.123,
      "fetched_at": "2026-05-08T12:00:00+00:00",
      "regions": {"01ds": "dolnośląskie", ...}
    }
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from polish_genealogy_mcp.sources.geneteka.constants import REGIONS as FALLBACK_REGIONS

if TYPE_CHECKING:
    from polish_genealogy_mcp.sources.geneteka.client import GenetekaClient

_REGION_LINK_RE = re.compile(r'<a[^>]*\bw=([0-9a-z]+)[^"]*"[^>]*>([^<]+)</a>')

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def _ttl_seconds() -> float:
    raw = os.environ.get("GENETEKA_REGIONS_TTL_DAYS")
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        days = float(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return max(0.0, days) * 24 * 3600


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "polish-genealogy-mcp" / "geneteka_regions.json"


def parse_regions(html: str) -> dict[str, str]:
    """Extract `{code: name}` from the surname-occurrence form HTML.

    Each region appears as several links (overall + births/deaths/marriages);
    we keep the first occurrence, which is the human-readable region name.
    """
    seen: dict[str, str] = {}
    for code, name in _REGION_LINK_RE.findall(html):
        seen.setdefault(code, name.strip())
    return seen


def load_cached(
    path: Path | None = None, *, ttl_seconds: float | None = None
) -> dict[str, str] | None:
    """Return the cached regions if the file exists and is younger than TTL."""
    path = path or default_cache_path()
    if not path.exists():
        return None
    ttl = _ttl_seconds() if ttl_seconds is None else ttl_seconds
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(payload.get("fetched_at_epoch", 0))
        regions = payload.get("regions")
    except Exception:
        return None
    if time.time() - fetched_at > ttl:
        return None
    if isinstance(regions, dict) and regions:
        return {str(k): str(v) for k, v in regions.items()}
    return None


def save_cache(regions: dict[str, str], path: Path | None = None) -> None:
    """Atomically persist the regions table for later re-use."""
    path = path or default_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_epoch": time.time(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def fetch_regions(client: "GenetekaClient") -> dict[str, str]:
    """Fetch the form page through `client` and parse it. Raises on empty result."""
    html = client.get_regions_html()
    parsed = parse_regions(html)
    if not parsed:
        raise RuntimeError("Geneteka regions page returned no recognizable region links")
    return parsed


def get_regions(client: "GenetekaClient", *, cache_path: Path | None = None) -> dict[str, str]:
    """Cache-first region lookup with graceful fallback.

    Order of preference:
      1. Fresh cache (younger than TTL).
      2. Live fetch — written to cache on success.
      3. Stale cache (any age) — better than nothing.
      4. Hardcoded `FALLBACK_REGIONS` — guaranteed non-empty.
    """
    cache_path = cache_path or default_cache_path()

    cached = load_cached(cache_path)
    if cached is not None:
        return cached

    try:
        fresh = fetch_regions(client)
        try:
            save_cache(fresh, cache_path)
        except OSError:
            pass  # cache is best-effort; never fail the call over it
        return fresh
    except Exception:
        stale = load_cached(cache_path, ttl_seconds=float("inf"))
        if stale is not None:
            return stale
        return dict(FALLBACK_REGIONS)
