"""Genealogy Indexer parser tests against a captured real-world response.

The fixtures under ``tests/fixtures/genealogyindexer/`` were fetched once:

* ``search_szumiec.html`` — a bare ``Szumiec`` search (no place/collection
  filter, no transliteration). 46 matches across 43 source pages, mixing
  plain-text directory snippets with two tabular Address-Directory pages
  (one of which groups four rows onto a single scanned page).
* ``search_no_matches.html`` — a gibberish term that returns "No matches".
"""

from __future__ import annotations

from pathlib import Path

from genealogy_mcp.sources.genealogyindexer.parser import parse_search_response

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "genealogyindexer"


def _read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8", errors="replace")


def _result(name: str = "search_szumiec.html", **kw):
    return parse_search_response(_read(name), query="Szumiec", **kw)


def test_total_returned_and_grouping():
    r = _result()
    # The site reports 46 individual matches; they are grouped onto 43
    # source-page items (one tabular page carries four matching rows).
    assert r.total == 46
    assert r.returned == 43
    assert len(r.items) == 43
    assert r.truncated is False


def test_text_snippet_item_full_fields():
    r = _result()
    it = next(x for x in r.items if x.source_id == "d357")
    assert it.title == "1938 Polish Public Companies, Industry, and Trade"
    assert it.image_label == "image 181"
    assert it.image_number == 181
    assert it.scan_url == (
        "https://crispa.uw.edu.pl/object/files/318782/display/Default?pageNumber=181"
    )
    assert it.images_from == "University of Warsaw Digital Library"
    assert it.images_from_url == "https://crispa.uw.edu.pl/object/files/318782/display/Default"
    assert it.date_added == "2 Apr 2012"
    assert it.source_title and it.source_title.startswith("Rocznik Polskiego Przemysłu")
    assert it.entries == []
    assert it.snippets
    # The matched term is wrapped in bold so the agent can spot it in context.
    assert "**Szumieć**" in it.snippets[0]


def test_table_item_groups_rows_into_entries():
    r = _result()
    it = next(x for x in r.items if x.source_id == "d689" and len(x.entries) == 4)
    assert it.title == "1931-1939 Radzyn Podlaski Address Directory (D. Magier; 2013)"
    assert it.image_number == 252
    assert it.snippets == []
    assert [e["First Name"] for e in it.entries] == [
        "Jan",
        "Helena",
        "Franciszek",
        "Leokadia",
    ]
    first = it.entries[0]
    assert first["Number"] == "6579"
    assert first["Last Name"] == "Szumieć"
    assert first["Occupation"] == "przy rodzicach"
    assert "Kozirynek" in first["Address"]


def test_relative_scan_urls_are_resolved_absolute():
    r = _result()
    it = next(x for x in r.items if x.source_id == "d689" and len(x.entries) == 4)
    # The page links to the in-site /frame viewer; it must come back absolute.
    assert it.scan_url == "https://genealogyindexer.org/frame/d689/252"


def test_max_results_caps_items_and_flags_truncation():
    r = _result(max_results=5)
    assert r.total == 46
    assert r.returned == 5
    assert len(r.items) == 5
    assert r.truncated is True


def test_no_matches_returns_empty_without_raising():
    r = parse_search_response(_read("search_no_matches.html"), query="zzxqwkjvbnmqq")
    assert r.total == 0
    assert r.items == []
    assert r.returned == 0
    assert r.truncated is False


def test_changed_or_truncated_page_raises():
    import pytest

    with pytest.raises(ValueError, match="Matches Found"):
        parse_search_response("<html><body>an unrelated page</body></html>")
