"""Tests for the GEDCOM source: parsing, querying, and server registration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from genealogy_mcp.server import build_server
from genealogy_mcp.sources.gedcom import queries
from genealogy_mcp.sources.gedcom.parser import load

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ged"


GEDCOM_TOOLS = {
    "gedcom_search_persons",
    "gedcom_get_person",
    "gedcom_get_family",
    "gedcom_search_events",
    "gedcom_get_event",
    "gedcom_search_places",
    "gedcom_search_sources",
    "gedcom_get_source",
}


@pytest.fixture(scope="module")
def store():
    return load(FIXTURE)


def test_load_counts(store):
    assert len(store.persons) == 5
    assert len(store.families) == 2
    assert len(store.sources) == 1
    # Each person has BIRT, three have spouses, two have DEAT/MARR mix.
    assert any(ev.tag == "BIRT" for ev in store.events.values())
    assert any(ev.tag == "MARR" for ev in store.events.values())


def test_parent_resolution(store):
    piotr = store.persons["@I3@"]
    assert piotr.father_id == "@I1@"
    assert piotr.mother_id == "@I2@"
    ewa = store.persons["@I5@"]
    assert ewa.father_id == "@I3@"
    assert ewa.mother_id == "@I4@"


def test_search_persons_by_surname(store):
    res = queries.search_persons(store, surname="kowalsk")
    ids = {p.id for p in res.items}
    # Surname match is substring on folded form: matches Kowalski and Kowalska.
    assert {"@I1@", "@I3@", "@I5@"}.issubset(ids)


def test_search_persons_diacritic_insensitive(store):
    res = queries.search_persons(store, surname="wisniewska")
    assert any(p.id == "@I4@" for p in res.items)


def test_search_persons_year_filter(store):
    res = queries.search_persons(store, born_after=1950, born_before=1960)
    assert {p.id for p in res.items} == {"@I5@"}


def test_search_persons_place_filter(store):
    res = queries.search_persons(store, place="lublin")
    assert {p.id for p in res.items} == {"@I4@", "@I5@"}


def test_get_person_includes_events_and_unions(store):
    detail = queries.get_person(store, "@I1@")
    assert detail is not None
    tags = {ev.tag for ev in detail.events}
    assert {"BIRT", "DEAT", "OCCU"}.issubset(tags)
    assert detail.n_unions == 1
    assert detail.unions[0].id == "@F1@"


def test_get_family(store):
    family = queries.get_family(store, "@I3@")
    assert family is not None
    assert family.father.id == "@I1@"
    assert family.mother.id == "@I2@"
    assert {u.id for u in family.unions} == {"@F2@"}
    assert {c.id for c in family.children_by_union["@F2@"]} == {"@I5@"}


def test_search_events_by_tag(store):
    res = queries.search_events(store, tag="MARR")
    assert res.total == 2
    assert {e.tag for e in res.items} == {"MARR"}


def test_get_event(store):
    detail = queries.get_event(store, "@F1@:MARR")
    assert detail is not None
    assert detail.year == 1925
    assert detail.place.name == "Warszawa, Polska"


def test_search_places(store):
    res = queries.search_places(store, "warszawa")
    names = {p.name for p in res.items}
    assert "Warszawa, Polska" in names


def test_search_sources(store):
    res = queries.search_sources(store, "parafialne")
    assert res.total == 1
    assert res.items[0].id == "@S1@"


def test_build_server_registers_gedcom_tools():
    server = build_server(
        gedcom_path=FIXTURE,
        enable_geneteka=False,
        enable_genealogia_w_archiwach=False,
        enable_genpod=False,
        enable_genbaza=False,
        enable_lubgens=False,
    )
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert GEDCOM_TOOLS.issubset(names)


def test_build_server_rejects_missing_gedcom(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_server(gedcom_path=tmp_path / "missing.ged")
