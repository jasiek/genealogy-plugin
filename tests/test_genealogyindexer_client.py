"""Genealogy Indexer client tests — request shape and arg validation, offline.

Uses ``httpx.MockTransport`` so no network call is made; the mock captures
the POST body and replays a captured fixture as the response.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from genealogy_mcp.sources.genealogyindexer.client import (
    GenealogyIndexerClient,
    GenealogyIndexerConfig,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "genealogyindexer"
FIXTURE = (FIXTURES / "search_szumiec.html").read_bytes()


def _client(handler) -> GenealogyIndexerClient:
    cfg = GenealogyIndexerConfig(min_interval_seconds=0.0)
    return GenealogyIndexerClient(cfg, transport=httpx.MockTransport(handler))


def test_search_posts_form_with_mapped_fields():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).rstrip("/") == "https://genealogyindexer.org"
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        result = client.search(
            term="Szumiec",
            place="Poland",
            collection="directories",
            date="1919_1945",
            match="soundex",
            sort="newest",
            transliteration="add_cyrillic",
        )

    assert captured["term"] == "Szumiec"
    assert captured["search"] == "1"
    assert captured["scope"] == "1000"  # "Poland" -> top-level code
    assert captured["collection"] == "directories"
    assert captured["date"] == "1945"
    assert captured["match"] == "dm"
    assert captured["sort"] == "newness"
    assert captured["transliteration"] == "addcyr"
    # The fixture parses cleanly.
    assert result.total == 46


def test_any_place_and_defaults():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        client.search(term="Kowalski")

    assert captured["scope"] == "any"
    assert captured["collection"] == "any"
    assert captured["date"] == "any"
    assert captured["match"] == "regular"
    assert captured["sort"] == "dist"
    assert captured["transliteration"] == "none"


def test_raw_scope_code_passes_through():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=FIXTURE)

    with _client(handler) as client:
        client.search(term="Szumiec", place="+1100")  # multinational Galicia

    assert captured["scope"] == "+1100"


def test_empty_term_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not issue a request")

    with _client(handler) as client:
        with pytest.raises(ValueError, match="non-empty term"):
            client.search(term="   ")


def test_unknown_enum_and_place_values_raise():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not issue a request")

    with _client(handler) as client:
        with pytest.raises(ValueError, match="collection"):
            client.search(term="X", collection="phonebooks")
        with pytest.raises(ValueError, match="match"):
            client.search(term="X", match="fuzzy")
        with pytest.raises(ValueError, match="[Uu]nknown place"):
            client.search(term="X", place="Atlantis")
