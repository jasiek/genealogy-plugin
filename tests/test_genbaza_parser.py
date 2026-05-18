"""Genbaza parser tests using captured real-world HTML fragments.

Fixtures live in tests/fixtures/genbaza/ and were fetched once with a
manual delay between requests to respect the source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from genealogy_mcp.sources.genbaza.parser import (
    parse_resources_response,
    parse_search_response,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "genbaza"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---- Variant A (10-column) sites -----------------------------------------


def test_swietogen_search_extracts_records_counts_and_pages():
    result = parse_search_response(
        _read("swietogen_search.html"), site="swietogen", requested_record_type=1
    )
    assert result.site == "swietogen"
    assert result.record_type == "birth"
    assert result.counts == {"birth": 6156, "marriage": 3230, "death": 4188}
    assert result.total_pages == 62
    assert len(result.items) > 0


def test_swietogen_search_carries_scan_url_for_indexed_scans():
    result = parse_search_response(
        _read("swietogen_search.html"), site="swietogen", requested_record_type=1
    )
    first = result.items[0]
    assert first.surname == "Kowalski"
    assert first.parish == "Sosnowiec - KLS"
    assert first.scan_url == "https://metryki.genbaza.pl/genbaza,list,500385,1"
    assert first.indexer == "More Maiorum"
    # The Year column on this row is "0" — the upstream's sentinel for
    # "year unknown". We surface it as None, not 0.
    assert first.year is None


def test_swietogen_search_falls_back_to_archive_ref_without_scan():
    result = parse_search_response(
        _read("swietogen_search.html"), site="swietogen", requested_record_type=1
    )
    notariat = next(r for r in result.items if r.parish and "notariat" in r.parish)
    assert notariat.scan_url is None
    assert notariat.archive_ref and notariat.archive_ref.startswith("AP Kielce")


def test_swietogen_no_results_returns_empty_items_with_zero_counts():
    result = parse_search_response(
        _read("swietogen_no_results.html"), site="swietogen", requested_record_type=1
    )
    assert result.items == []
    assert result.counts == {"birth": 0, "marriage": 0, "death": 0}


def test_pomerania_search_uses_pur_archive_refs():
    result = parse_search_response(
        _read("pomerania_search.html"), site="pomerania", requested_record_type=1
    )
    assert result.record_type == "birth"
    assert result.counts.get("birth", 0) > 0
    assert any(r.archive_ref and "AP Szczecin" in r.archive_ref for r in result.items)


def test_warmia_search_handles_minimal_result_set():
    result = parse_search_response(
        _read("warmia_search.html"), site="warmia", requested_record_type=1
    )
    assert result.counts.get("birth") == 2
    # Tiny tables must still parse without error; rows may or may not
    # be present depending on what the upstream returned.
    assert isinstance(result.items, list)


# ---- Variant B (7-column) sites ------------------------------------------


def test_kurpie_uses_combined_table_with_year_in_notes():
    result = parse_search_response(
        _read("kurpie_search.html"), site="kurpie", requested_record_type=1
    )
    # Variant B has one combined table — no per-type counts, no
    # record_type label.
    assert result.record_type is None
    assert result.counts == {"total": 327}
    assert len(result.items) > 0
    first = result.items[0]
    # Year is buried in the notes cell as "Rok: NNNN".
    assert first.year == 1913
    assert first.given_name == "Tadeusz"
    # The surname cell carries an alternative-name marker; both forms
    # are surfaced as a single string after tag stripping.
    assert "Konarski" in (first.surname or "")
    # Variant B sets archive_ref via the "Źródło:" key.
    assert first.archive_ref and "APW" in first.archive_ref
    assert first.indexer == "Elżbieta Misiewicz"


def test_polishgenealogy_no_results_returns_empty_items():
    result = parse_search_response(
        _read("polishgenealogy_empty.html"),
        site="polishgenealogy",
        requested_record_type=1,
    )
    assert result.items == []


# ---- Resources catalogue --------------------------------------------------


def test_resources_lists_parishes_with_year_ranges():
    result = parse_resources_response(_read("swietogen_resources.html"), site="swietogen")
    assert result.summary and "Urodzenia" in result.summary
    assert len(result.items) > 100
    by_name = {r.parish: r for r in result.items}
    baltow = by_name.get("Bałtów")
    assert baltow is not None
    assert baltow.births and "1797" in baltow.births


def test_unknown_record_type_falls_back_to_label_from_response():
    # Caller passed an unknown rodz; the response's "Tabela z wynikami
    # dla urodzeń" label still wins.
    result = parse_search_response(
        _read("swietogen_search.html"), site="swietogen", requested_record_type=999
    )
    assert result.record_type == "birth"


@pytest.mark.parametrize(
    "fixture, site",
    [
        ("swietogen_search.html", "swietogen"),
        ("kurpie_search.html", "kurpie"),
        ("pomerania_search.html", "pomerania"),
        ("warmia_search.html", "warmia"),
    ],
)
def test_every_returned_record_carries_site_field(fixture, site):
    result = parse_search_response(_read(fixture), site=site, requested_record_type=1)
    assert all(r.site == site for r in result.items)
