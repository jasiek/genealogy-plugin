"""Tests for the Geneteka region catalogue: parser + on-disk weekly cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from genealogy_mcp.sources.geneteka import regions as regions_mod

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def form_html() -> str:
    return (FIXTURES / "geneteka_se_form.html").read_text(encoding="utf-8")


def test_parse_regions_extracts_all_known_codes(form_html):
    parsed = regions_mod.parse_regions(form_html)
    # 16 voivodeships + Ukraine, Belarus, Lithuania, Pozostałe, Warszawa = 21
    assert len(parsed) >= 21
    assert parsed["05ld"] == "łódzkie"
    assert parsed["02kp"] == "kujawsko-pomorskie"
    assert parsed["21uk"] == "Ukraina"
    assert parsed["71wa"] == "Warszawa"


def test_parse_regions_empty_html_returns_empty():
    assert regions_mod.parse_regions("") == {}
    assert regions_mod.parse_regions("<html><body>nothing</body></html>") == {}


def test_save_and_load_roundtrip(tmp_path):
    cache = tmp_path / "regions.json"
    regions_mod.save_cache({"05ld": "łódzkie"}, path=cache)
    assert cache.exists()
    loaded = regions_mod.load_cached(cache)
    assert loaded == {"05ld": "łódzkie"}


def test_load_cached_returns_none_for_missing(tmp_path):
    assert regions_mod.load_cached(tmp_path / "missing.json") is None


def test_load_cached_returns_none_for_stale(tmp_path):
    cache = tmp_path / "regions.json"
    payload = {
        "fetched_at_epoch": time.time() - (regions_mod.DEFAULT_TTL_SECONDS + 1),
        "regions": {"05ld": "łódzkie"},
    }
    cache.write_text(json.dumps(payload), encoding="utf-8")
    assert regions_mod.load_cached(cache) is None


def test_load_cached_accepts_stale_when_ttl_infinite(tmp_path):
    """Used as the second-tier fallback in get_regions on fetch failure."""
    cache = tmp_path / "regions.json"
    payload = {
        "fetched_at_epoch": 1.0,  # ancient
        "regions": {"05ld": "łódzkie"},
    }
    cache.write_text(json.dumps(payload), encoding="utf-8")
    assert regions_mod.load_cached(cache, ttl_seconds=float("inf")) == {"05ld": "łódzkie"}


def test_load_cached_returns_none_for_corrupt(tmp_path):
    cache = tmp_path / "regions.json"
    cache.write_text("not json {", encoding="utf-8")
    assert regions_mod.load_cached(cache) is None


def test_get_regions_uses_fresh_cache_without_calling_client(tmp_path):
    cache = tmp_path / "regions.json"
    regions_mod.save_cache({"05ld": "łódzkie"}, path=cache)

    client = MagicMock()
    out = regions_mod.get_regions(client, cache_path=cache)
    assert out == {"05ld": "łódzkie"}
    client.get_regions_html.assert_not_called()


def test_get_regions_fetches_when_cache_missing(tmp_path, form_html):
    cache = tmp_path / "regions.json"
    client = MagicMock()
    client.get_regions_html.return_value = form_html

    out = regions_mod.get_regions(client, cache_path=cache)
    assert "05ld" in out
    client.get_regions_html.assert_called_once()
    # Cache was written for next time.
    assert cache.exists()
    assert "05ld" in regions_mod.load_cached(cache)


def test_get_regions_falls_back_to_stale_cache_on_fetch_failure(tmp_path):
    cache = tmp_path / "regions.json"
    payload = {
        "fetched_at_epoch": 1.0,  # ancient — past TTL
        "regions": {"05ld": "łódzkie"},
    }
    cache.write_text(json.dumps(payload), encoding="utf-8")

    client = MagicMock()
    client.get_regions_html.side_effect = RuntimeError("network down")

    out = regions_mod.get_regions(client, cache_path=cache)
    assert out == {"05ld": "łódzkie"}


def test_get_regions_falls_back_to_hardcoded_when_no_cache_and_fetch_fails(tmp_path):
    cache = tmp_path / "regions.json"
    client = MagicMock()
    client.get_regions_html.side_effect = RuntimeError("network down")

    out = regions_mod.get_regions(client, cache_path=cache)
    # Hardcoded REGIONS in constants.py covers all 21 codes.
    assert "05ld" in out
    assert len(out) >= 21
