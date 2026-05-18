"""Tests for the layout-detection and Layout B heuristics in the
genbaza resource-catalogue CSV scraper.

Layout A (parish: swietogen/pomerania/warmia) is exercised end-to-end
via the fixture round-trip; Layout B (archival: kurpie/polishgenealogy)
gets unit coverage for the description classifier and place extractor,
plus a fixture-based smoke test.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from polish_genealogy_mcp.scrapers.common import CsvSink

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "genbaza_resources_csv.py"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "genbaza"


def _load_module():
    spec = importlib.util.spec_from_file_location("genbaza_resources_csv", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


M = _load_module()


def test_classify_birth_marriage_death():
    assert M.classify_layout_b_description("Srokowo - urodzenia 1883-1913") == "Chrzty"
    assert M.classify_layout_b_description("Wielbark - małżeństwa 1877-1905") == "Śluby"
    assert M.classify_layout_b_description("Srokowo - zgony 1883") == "Zgony"
    assert M.classify_layout_b_description("lista zmarłych, rachunek pokladnego") == "Zgony"


def test_classify_excludes_resident_lists_and_archival_series():
    assert (
        M.classify_layout_b_description("Brzozówka - lista mieszkańców urodzonych do 1920") is None
    )
    assert M.classify_layout_b_description("Rejestr mieszkańców gminy Mały Płock") is None
    assert M.classify_layout_b_description("Szczuczyn notariaty- sygnatura 57-14") is None
    assert M.classify_layout_b_description("Nawiady - Grundbuch księga gruntowa sygn.6637") is None


def test_classify_unknown_returns_none():
    assert M.classify_layout_b_description("") is None
    assert M.classify_layout_b_description("Spisy rekrutów 1908") is None


def test_layout_b_place_dash_split():
    assert M.layout_b_place("Rodele- Rodehlen- urodzenia 1884-1885") == "Rodele"
    assert (
        M.layout_b_place("Srokowo – Drengfurh pow. kętrzyński- urodzenia 1883- 1913") == "Srokowo"
    )
    assert (
        M.layout_b_place("Willenberg Wielbark- miasto małżeństwa 1877-1905")
        == "Willenberg Wielbark"
    )


def test_layout_b_place_strips_polishgenealogy_prefix():
    assert M.layout_b_place("Lista urodzonych, Brodowe Łąki 1826-1844") == "Brodowe Łąki"
    assert M.layout_b_place("lista małżeństw, Księży Lasek 1877-1907") == "Księży Lasek"
    assert M.layout_b_place("Lista małżeństw, USC Myszyniec 1895-1910") == "USC Myszyniec"


def test_detect_layout_distinguishes_parish_and_archival():
    swietogen_body = (_FIXTURE_DIR / "swietogen_resources.html").read_text(encoding="utf-8")
    warmia_body = (_FIXTURE_DIR / "warmia_resources.html").read_text(encoding="utf-8")
    kurpie_body = (_FIXTURE_DIR / "kurpie_resources.html").read_text(encoding="utf-8")
    polishgen_body = (_FIXTURE_DIR / "polishgenealogy_resources.html").read_text(encoding="utf-8")
    assert M.detect_layout(swietogen_body) == "A"
    assert M.detect_layout(warmia_body) == "A"
    assert M.detect_layout(kurpie_body) == "B"
    assert M.detect_layout(polishgen_body) == "B"


def _emit_to_string(body: str, host: str) -> list[str]:
    buf = io.StringIO()
    sink = CsvSink.__new__(CsvSink)
    sink.output = None
    sink.fieldnames = M.FIELDNAMES
    sink.row_count = 0
    sink._owns_handle = False
    sink._handle = buf
    import csv

    sink._writer = csv.DictWriter(buf, fieldnames=M.FIELDNAMES)
    sink._writer.writeheader()
    M.emit_for_host(body, host, sink)
    return buf.getvalue().splitlines()


def test_warmia_fixture_yields_three_year_ranges():
    body = (_FIXTURE_DIR / "warmia_resources.html").read_text(encoding="utf-8")
    lines = _emit_to_string(body, "warmia")
    data = lines[1:]
    assert len(data) == 3
    assert all(row.startswith("Biskupiec Reszelski,Biskupiec Reszelski,") for row in data)


def test_kurpie_fixture_only_parish_records():
    body = (_FIXTURE_DIR / "kurpie_resources.html").read_text(encoding="utf-8")
    lines = _emit_to_string(body, "kurpie")
    data = lines[1:]
    assert data, "expected at least one classified row"
    # The "lista mieszkańców urodzonych do 1920" rows must NOT slip
    # through the classifier — they're resident registers, not baptism
    # books.
    assert all("Brzozówka" not in row for row in data)
    assert all("lista mieszk" not in row.lower() for row in data)
    # And the Srokowo birth rows we hand-verified should be there.
    assert any(row.startswith("Srokowo,Srokowo,Chrzty,1888,1888,") for row in data)
