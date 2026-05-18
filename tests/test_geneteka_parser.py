"""Geneteka parser tests using captured real-world API payloads.

These tests must stay offline — fixtures live in tests/fixtures/ and were
fetched once with a 5–10s gap to respect the source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genealogy_mcp.sources.geneteka.parser import (
    _parse_uwagi,
    parse_rows,
    parse_total,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def births_payload() -> dict:
    return json.loads((FIXTURES / "geneteka_births.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def marriages_payload() -> dict:
    return json.loads((FIXTURES / "geneteka_marriages.json").read_text(encoding="utf-8"))


def test_parse_total_coerces_string(births_payload):
    assert parse_total(births_payload) == int(births_payload["recordsFiltered"])


def test_parse_total_handles_missing():
    assert parse_total({}) == 0
    assert parse_total({"recordsFiltered": "abc"}) == 0


def test_parse_births_basic(births_payload):
    rows = births_payload["data"]
    parsed = parse_rows(rows, "birth", "05ld")
    assert len(parsed) == len(rows)

    first = parsed[0]
    assert first.record_type == "birth"
    assert first.region_code == "05ld"
    assert first.year == 1852
    assert first.act_no == "21"
    assert first.person.given_name == "Józefa"
    assert first.person.surname == "Janowska"
    assert first.person.father_given == "Wincenty"
    assert first.person.mother_given == "Aniela"
    assert first.person.mother_maiden == "Kowalewska"
    assert first.parish == "Solca Wielka"
    assert first.place == "Solca Mała"
    assert first.spouse is None


def test_parse_births_extract_uwagi(births_payload):
    parsed = parse_rows(births_payload["data"], "birth", "05ld")
    first = parsed[0]
    # gid is the stable Geneteka record id used by fix.php
    assert first.gid == 9962424
    # Free-text comment carries the exact birth date
    assert first.comments and "Data urodzenia" in first.comments
    # Archive / indexer / fix URL all extracted
    assert first.archive and "Archiwum" in first.archive
    assert first.indexer == "Stawska_Mirosława"
    assert first.fix_url and "fix.php?gid=9962424" in first.fix_url


def test_parse_marriages_layout(marriages_payload):
    rows = marriages_payload["data"]
    parsed = parse_rows(rows, "marriage", "05ld")
    assert len(parsed) == len(rows)

    first = parsed[0]
    assert first.record_type == "marriage"
    assert first.year == 1853
    assert first.act_no == "4"
    # groom in `person`, bride in `spouse`
    assert first.person.given_name == "Tomasz"
    assert first.person.surname == "Kowalski"
    assert first.person.parents == "Jan, Małgorzata"
    assert first.spouse is not None
    assert first.spouse.given_name == "Franciszka"
    assert first.spouse.surname == "Załoga"
    assert first.spouse.parents == "Łukasz, Katarzyna"
    assert first.parish == "Lgota Wielka"
    assert first.place is None  # marriage rows have no separate Miejscowość
    assert first.gid == 2419609


def test_parse_uwagi_handles_empty():
    out = _parse_uwagi(None)
    assert all(v is None for v in out.values())
    out2 = _parse_uwagi("")
    assert all(v is None for v in out2.values())


def test_parse_uwagi_dedupes_fix_label():
    """The "Zgłoś poprawkę" tooltip must not leak into comments."""
    raw = (
        '<img src="images/i.png" title=" &#013;Wiek: 60 lat ">'
        '<a href="fix.php?gid=42&bdm=D" target="_blank">'
        '<img src="images/fix.png" title="Zgłoś poprawkę"></a>'
    )
    out = _parse_uwagi(raw)
    assert out["gid"] == 42
    assert out["comments"] == "Wiek: 60 lat"
    assert out["archive"] is None
