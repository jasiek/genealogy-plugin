"""Lubgens parser tests using a captured real-world response.

The fixture in ``tests/fixtures/lubgens/search_kowalski.html`` was
fetched once with a manual delay between requests to respect the source.
It is a saturated query (all three categories truncated at 500 rows),
which exercises the truncation-detection path.
"""

from __future__ import annotations

from pathlib import Path

from polish_genealogy_mcp.sources.lubgens.parser import parse_search_response

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lubgens"


def _read(name: str) -> str:
    # The upstream emits a few stray non-UTF-8 bytes where its highlight
    # <span> wrappers split a multi-byte character; mirror what the
    # client does and decode tolerantly.
    return (FIXTURES / name).read_bytes().decode("utf-8", errors="replace")


def test_parses_all_three_sections_and_marks_truncation():
    result = parse_search_response(_read("search_kowalski.html"), surname_query="kowalski")
    assert result.counts == {"birth": 500, "marriage": 500, "death": 500}
    assert result.truncated == {"birth": True, "marriage": True, "death": True}
    by_type = {
        t: [r for r in result.items if r.record_type == t] for t in ("birth", "marriage", "death")
    }
    # 500 data rows + a header row in each section.
    assert len(by_type["birth"]) == 500
    assert len(by_type["marriage"]) == 500
    assert len(by_type["death"]) == 500


def test_birth_row_has_scan_url_and_extracts_parents():
    result = parse_search_response(_read("search_kowalski.html"))
    first_birth = next(r for r in result.items if r.record_type == "birth")
    assert first_birth.surname == "Kowalski"
    assert first_birth.given_name == "Stanisław"
    assert first_birth.parish == "Abramowice"
    assert first_birth.act_number == "41"
    assert first_birth.year == 1813
    assert first_birth.scan_url and first_birth.scan_url.startswith(
        "https://szukajwarchiwach.gov.pl/skan/"
    )
    assert first_birth.father_name == "Michał"
    assert first_birth.mother_name == "Wiktoria Goljan"


def test_marriage_row_carries_both_spouses_and_grooms_parents():
    result = parse_search_response(_read("search_kowalski.html"))
    first = next(r for r in result.items if r.record_type == "marriage")
    assert first.surname == "Kowalski"
    assert first.given_name == "Stanisław"
    assert first.spouse_surname == "Zdunek"
    assert first.spouse_given_name == "Marianna"
    assert first.parish == "Abramów"
    assert first.year == 1930
    assert first.scan_url and "familysearch.org" in first.scan_url

    # Find a marriage where the notes use the explicit On-/Ona- markers.
    explicit = next(
        r
        for r in result.items
        if r.record_type == "marriage" and r.notes and "On-" in r.notes and "O:" in r.notes
    )
    assert explicit.father_name is not None
    assert explicit.mother_name is not None


def test_death_row_extracts_father_and_mother_when_present():
    result = parse_search_response(_read("search_kowalski.html"))
    first = next(r for r in result.items if r.record_type == "death")
    assert first.surname == "Kowalski"
    assert first.given_name == "Jan"
    assert first.parish == "Abramów"
    assert first.year == 1928
    assert first.father_name == "Edward Kowalski"
    assert first.mother_name == "Anna Rodak"


def test_act_zero_normalised_to_none():
    result = parse_search_response(_read("search_kowalski.html"))
    zero = next(
        r for r in result.items if r.record_type == "marriage" and r.given_name == "Aleksander"
    )
    assert zero.act_number is None
