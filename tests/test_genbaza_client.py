"""Offline tests for the genbaza HTTP client.

The client is exercised via an httpx MockTransport so every test stays
hermetic — no real network. We assert on the request shape (URL host,
path, query encoding) and on the parsed response.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from polish_genealogy_mcp.sources.genbaza.client import (
    GenbazaClient,
    GenbazaConfig,
    pl2uni,
)
from polish_genealogy_mcp.sources.genbaza.constants import SITES

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "genbaza"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client_with(handler) -> GenbazaClient:
    return GenbazaClient(
        GenbazaConfig(min_interval_seconds=0),
        transport=httpx.MockTransport(handler),
    )


def test_pl2uni_replaces_polish_diacritics():
    assert pl2uni("Bałtów") == "Bax322tx243w"
    assert pl2uni("Łódź") == "x321x243dx378"
    assert pl2uni("Kowalski") == "Kowalski"


def test_search_sends_pl2uni_encoded_params_to_correct_host():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_read("swietogen_search.html"))

    with _client_with(handler) as client:
        result = client.search(
            "swietogen",
            surname="Bałtów",  # Polish chars to verify encoding
            page=2,
            record_type="birth",
        )

    assert len(seen) == 1
    req = seen[0]
    assert req.url.host == "swietogen.genbaza.pl"
    assert req.url.path == "/php/getdata.php"
    qs = dict(req.url.params)
    assert qs["naz"] == "Bax322tx243w"
    assert qs["pag"] == "2"
    assert qs["rodz"] == "1"
    # The cookie banner gate must always be set, otherwise the upstream
    # serves a stripped response.
    assert req.headers.get("cookie", "").find("agree=1") != -1
    assert result.page == 2
    assert result.site == "swietogen"


def test_search_marriage_uses_rodz_3():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_read("warmia_search.html"))

    with _client_with(handler) as client:
        client.search("warmia", surname="Kowalski", record_type="marriage")

    assert dict(seen[0].url.params)["rodz"] == "3"


def test_list_resources_sets_zasob_1():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_read("swietogen_resources.html"))

    with _client_with(handler) as client:
        result = client.list_resources("swietogen")

    assert dict(seen[0].url.params)["zasob"] == "1"
    assert result.site == "swietogen"
    assert len(result.items) > 0


def test_search_unknown_site_raises():
    with _client_with(lambda r: httpx.Response(200, text="")) as client:
        with pytest.raises(ValueError, match="Unknown genbaza site"):
            client.search("nonexistent", surname="x")


def test_search_uses_referer_matching_target_host():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_read("kurpie_search.html"))

    with _client_with(handler) as client:
        client.search("kurpie", surname="Kowalski")

    assert seen[0].headers["referer"] == "https://kurpie.genbaza.pl/"


def test_search_propagates_http_errors(monkeypatch):
    # Skip backoff between attempts to keep the test fast.
    monkeypatch.setenv("GENEALOGY_RETRY_BASE_DELAY", "0")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="oops")

    with _client_with(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.search("swietogen", surname="x")


def test_search_does_not_retry_non_5xx_errors():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404, text="missing")

    with _client_with(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.search("swietogen", surname="x")

    assert len(seen) == 1


def test_search_retries_transient_5xx_then_succeeds(monkeypatch):
    monkeypatch.setenv("GENEALOGY_RETRY_BASE_DELAY", "0")
    seen: list[httpx.Request] = []
    success = _read("swietogen_search.html")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, text=success)

    with _client_with(handler) as client:
        result = client.search("swietogen", surname="Kowalski")

    assert len(seen) == 3
    assert result.site == "swietogen"


def test_default_config_resolves_all_known_sites():
    sites = GenbazaConfig().sites
    for code in ("swietogen", "polishgenealogy", "warmia", "kurpie", "pomerania"):
        assert code in sites
        assert sites[code] == SITES[code]
