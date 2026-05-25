"""BaSIA client tests — request shape and arg validation, fully offline.

Uses ``httpx.MockTransport`` so no network call is made; the mock captures
the POST body and replays a captured fixture as the response.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from genealogy_mcp.sources.basia.client import BasiaClient, BasiaConfig

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "basia"
FIXTURE = (FIXTURES / "search_szumiec_births_1810_1830.html").read_bytes()


def _client(handler) -> BasiaClient:
    cfg = BasiaConfig(min_interval_seconds=0.0)
    return BasiaClient(cfg, transport=httpx.MockTransport(handler))


def test_search_posts_advanced_form_with_expected_fields():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).rstrip("/") == "https://basia.famula.pl"
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        result = client.search(
            surname="Szumiec",
            given_name="Jan",
            from_year=1810,
            to_year=1830,
            record_type="birth",
            sex="male",
            similarity=70,
        )

    assert captured["lname0"] == "Szumiec"
    assert captured["fname0"] == "Jan"
    assert captured["sex0"] == "m"
    assert captured["sim0"] == "70"
    assert captured["od"] == "1810"
    assert captured["do"] == "1830"
    assert captured["type_record"] == "a"
    # A record-type filter must flip the type toggle on, or it is ignored.
    assert captured["showtype"] == "block"
    assert captured["showplaces"] == "none"
    assert captured["search_ext"] == "szukaj"
    assert captured["p_count"] == "1"
    # The fixture is a real births page, so it parses cleanly.
    assert result.total == 11
    assert result.counts == {"birth": 11}


def test_place_toggles_showplaces_and_sends_distance():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        client.search(surname="Szumiec", place="Umień", distance_km=25)

    assert captured["showplaces"] == "block"
    assert captured["placename"] == "Umień"
    assert captured["distance"] == "25"
    # No record/unit filter -> type toggle stays off.
    assert captured["showtype"] == "none"


def test_year_defaults_fill_full_supported_range():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        client.search(surname="Szumiec")

    assert captured["od"] == "1577"
    assert int(captured["do"]) >= 2026


def test_empty_query_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not issue a request")

    with _client(handler) as client:
        with pytest.raises(ValueError, match="surname, given_name, or place"):
            client.search()


def test_unknown_enum_values_raise():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not issue a request")

    with _client(handler) as client:
        with pytest.raises(ValueError, match="record_type"):
            client.search(surname="X", record_type="baptism")
        with pytest.raises(ValueError, match="unit_type"):
            client.search(surname="X", unit_type="synagogue")
