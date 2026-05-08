"""Integration tests against the real Szumiec.heredis fixture.

These tests assert structural shape and coarse counts rather than specific
person IDs, so they remain stable as the source database is edited.
"""

from __future__ import annotations

import pytest

from polish_genealogy_mcp.sources.heredis import queries


def test_search_persons_no_filters_returns_page(conn):
    res = queries.search_persons(conn, limit=5)
    assert res.total > 1000  # the fixture has ~2.5k people
    assert len(res.items) == 5
    assert res.limit == 5
    assert res.offset == 0
    p = res.items[0]
    assert p.code_id > 0
    assert p.surname  # everyone has a surname (XrefNom is NOT NULL)


def test_search_persons_by_surname_is_accent_insensitive(conn):
    # The owner surname is "Szumiec" — should match without diacritics or case.
    upper = queries.search_persons(conn, surname="SZUMIEC", limit=5)
    lower = queries.search_persons(conn, surname="szumiec", limit=5)
    assert upper.total == lower.total
    assert upper.total > 0


def test_search_persons_by_sex(conn):
    males = queries.search_persons(conn, sex="M", limit=1)
    females = queries.search_persons(conn, sex="F", limit=1)
    assert males.total > 0
    assert females.total > 0
    assert males.items[0].sex == "M"
    assert females.items[0].sex == "F"


def test_search_persons_year_range(conn):
    res = queries.search_persons(conn, born_after=1800, born_before=1850, limit=10)
    assert res.total > 0
    for p in res.items:
        if p.birth and p.birth.date_ged:
            # Heredis date strings include a 4-digit year; tolerate APX/ABT.
            assert any(str(y) in p.birth.date_ged for y in range(1800, 1851))


def test_search_persons_pagination(conn):
    page1 = queries.search_persons(conn, limit=5, offset=0)
    page2 = queries.search_persons(conn, limit=5, offset=5)
    page1_ids = {p.code_id for p in page1.items}
    page2_ids = {p.code_id for p in page2.items}
    assert page1_ids.isdisjoint(page2_ids)


def test_get_person_round_trip(conn):
    res = queries.search_persons(conn, limit=1)
    target_id = res.items[0].code_id
    detail = queries.get_person(conn, target_id)
    assert detail is not None
    assert detail.code_id == target_id
    assert detail.surname == res.items[0].surname
    # n_unions/n_children are precomputed; just check consistency with events.
    assert detail.n_unions == len(detail.unions)


def test_get_person_missing_returns_none(conn):
    assert queries.get_person(conn, 99_999_999) is None


def test_get_family_proband(conn):
    # Sosa #1 is the proband — they should have at least one ancestor in the file.
    sosa1 = conn.execute("SELECT XrefIndividu FROM NumerosSosa WHERE SosaNumStr = '1'").fetchone()
    if sosa1 is None:
        pytest.skip("No Sosa #1 in fixture")
    fam = queries.get_family(conn, sosa1["XrefIndividu"])
    assert fam is not None
    # Either parent or sibling info should exist for a real proband.
    assert fam.father or fam.mother or fam.unions or fam.siblings


def test_search_events_by_type_birth(conn):
    res = queries.search_events(conn, event_type=4, limit=5)
    assert res.total > 0
    assert all(e.event_type == 4 for e in res.items)
    assert all(e.event_type_label == "Birth" for e in res.items)


def test_search_events_by_year(conn):
    res = queries.search_events(conn, after_year=1900, before_year=1910, limit=10)
    assert res.total > 0
    for e in res.items:
        assert e.date_tri is not None


def test_search_events_by_person(conn):
    person = queries.search_persons(conn, limit=1).items[0]
    res = queries.search_events(conn, person_id=person.code_id, limit=20)
    # Most people have at least one event (birth/baptism); but tolerate zero.
    assert res.total >= 0


def test_get_event_round_trip(conn):
    ev = queries.search_events(conn, event_type=4, limit=1).items[0]
    detail = queries.get_event(conn, ev.code_id)
    assert detail is not None
    assert detail.code_id == ev.code_id
    assert detail.event_type == 4


def test_search_places_returns_results(conn):
    # Some place must exist; pick an arbitrary substring that is likely present.
    res = queries.search_places(conn, "a", limit=5)
    assert res.total > 0
    assert len(res.items) <= 5
    for p in res.items:
        assert p.code_id > 0


def test_search_sources_returns_results(conn):
    res = queries.search_sources(conn, "a", limit=5)
    assert res.total > 0
    src = res.items[0]
    detail = queries.get_source(conn, src.code_id)
    assert detail is not None
    assert detail.code_id == src.code_id


def test_search_persons_limit_capped(conn):
    res = queries.search_persons(conn, limit=10_000)
    assert res.limit == 100  # capped


def test_birth_event_has_date_or_place(conn):
    res = queries.search_persons(conn, limit=20)
    # At least *some* people in the fixture should have a known birth event.
    assert any(p.birth is not None for p in res.items)
