"""BaSIA parser tests against captured real-world responses.

The fixtures under ``tests/fixtures/basia/`` were fetched once, with a
delay between requests, to respect the (slow) upstream:

* ``search_szumiec.html`` — bare surname "Szumiec"; a mixed result set
  (births, marriages, deaths, and "other" entries) that took ~83s.
* ``search_szumiec_births_1810_1830.html`` — the same surname narrowed to
  birth acts in 1810-1830, which returns only births and far faster.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from genealogy_mcp.sources.basia.parser import parse_search_response

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "basia"


def _read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8", errors="replace")


def _result(name: str = "search_szumiec.html", **kw):
    return parse_search_response(_read(name), surname_query="Szumiec", **kw)


def test_counts_total_and_search_time():
    r = _result()
    assert r.total == 83
    assert r.counts == {"birth": 31, "death": 30, "marriage": 15, "other": 7}
    assert r.search_time_seconds == pytest.approx(82.9)
    assert r.truncated is False


def test_birth_row_full_field_extraction():
    r = _result()
    b = next(x for x in r.items if x.record_id == "6744622")
    assert b.record_type == "birth"
    assert b.record_type_label == "akt urodzenia/chrztu"
    assert b.place == "Umień"
    assert b.unit_type == "par. rzymskokatolicka"
    assert b.year == 1815
    assert b.book_title == "Akta urodzonych, zaślubionych, zmarłych"
    assert b.name == "Michał" and b.given_name == "Michał" and b.surname is None
    assert b.father == "Jan Szołajski"
    assert b.mother == "Marianna Szumier"
    assert b.similarity == 78
    assert b.other_persons == ["Antoni Szałajski", "Piotr Rysiński"]
    assert "Konin" in (b.archive or "")
    assert b.signature == "821/6.1/5"
    assert b.scan_label == "821/6.1/5, skan 36"
    assert b.scan_url == (
        "https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/1831954#scan36"
    )
    assert b.indexer == "Rafał Kędziora"
    assert b.date_added == "2022-03-18"
    assert b.permalink == "https://basia.famula.pl/record/" + (
        "NTRfODIxXzYuMV81XzM2XzFfX18xODE1XzQ3NGJkMjA2YzEzYThiMTU4NTU4YWVlNWU4MjdhZDc0X2thdF9h"
    )


def test_marriage_captures_spouse_and_principal_parents():
    r = _result()
    m = next(x for x in r.items if x.record_type == "marriage")
    assert m.place == "Borysławice Kościelne"
    assert m.year == 1878
    assert m.name == "Józef Kawecki"
    assert m.father == "Franciszek Kawecki"
    assert m.mother == "Marianna"
    assert m.spouse == "Wiktorya Nitecka"


def test_death_extracts_age_parents_and_spouse():
    r = _result()
    d = next(x for x in r.items if x.record_id == "3255488")
    assert d.record_type == "death"
    assert d.name == "Łucya Maciejewska"
    assert d.age == "54 lat"
    assert d.father == "Ignacy Szumiel"
    assert d.mother == "Małgorzata"
    assert d.spouse == "Walenty"


def test_death_with_single_parent_does_not_swallow_spouse():
    r = _result()
    d = next(x for x in r.items if x.name and x.name.startswith("Teodora"))
    assert d.age == "23 lat"
    assert d.father == "Jan Zwolinski gospodarz"
    assert d.mother is None
    assert d.spouse == "Walenty Szumiła"


def test_other_entry_parses_terse_header_and_lists_people():
    r = _result()
    o = next(x for x in r.items if x.record_type == "other")
    assert o.record_type_label == "inne"
    assert o.place == "Dembe"
    assert o.year == 1831
    assert o.book_title == "Akta urodzeń, małżeństw i zgonu"
    assert o.name is None
    assert o.indexer_comment == "wypis urodzonych 1831"
    assert len(o.other_persons) == 23
    assert "Wojciech Augustyniak" in o.other_persons


def test_scan_urls_cover_both_szukajwarchiwach_domains():
    r = _result()
    hosts = {u.split("/")[2] for u in (x.scan_url for x in r.items) if u}
    assert "www.szukajwarchiwach.gov.pl" in hosts
    assert "szukajwarchiwach.pl" in hosts


def test_max_results_caps_items_and_flags_truncation():
    r = _result(max_results=10)
    assert r.total == 83
    assert len(r.items) == 10
    assert r.truncated is True
    # counts reflect the returned (capped) items.
    assert sum(r.counts.values()) == 10


def test_narrowed_births_fixture_returns_only_births():
    r = _result("search_szumiec_births_1810_1830.html")
    assert r.total == 11
    assert r.counts == {"birth": 11}
    assert r.search_time_seconds == pytest.approx(10.47)
    assert all(1810 <= (x.year or 0) <= 1830 for x in r.items)


def test_truncated_or_changed_page_raises():
    with pytest.raises(ValueError, match="timed out server-side"):
        parse_search_response("<html><body>just the form, no results</body></html>")
