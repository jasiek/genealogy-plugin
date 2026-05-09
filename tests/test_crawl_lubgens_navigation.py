from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "crawl_lubgens_navigation.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("crawl_lubgens_navigation", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_parish_links_extracts_navigation_parishes() -> None:
    module = load_script_module()
    html = """
    <div id='navigation'>
      <h2 class='head'>Annopol</h2>
      <ul>
        <li><a href='/viewpage.php?page_id=1052&par=81' class='side'>
          <img src='bullet.gif' /> <span>Annopol</span>
        </a></li>
        <li><a href='viewpage.php?page_id=1052&amp;par=74a' class='side'>
          <span>Annopol (mojż.)</span>
        </a></li>
      </ul>
      <h2 class='head'>USC Niedrzwica</h2>
      <ul>
        <li><a href='viewpage.php?page_id=1052&amp;par=' class='side'>
          <span>USC Niedrzwica</span>
        </a></li>
      </ul>
    </div>
    """

    rows = module.parse_parish_links(html, base_url="https://regestry.lubgens.eu/news.php")

    assert rows == [
        module.ParishLink(
            miejscowosc="ANNOPOL",
            label="Annopol",
            par_id="81",
            url="https://regestry.lubgens.eu/viewpage.php?page_id=1052&par=81",
        ),
        module.ParishLink(
            miejscowosc="ANNOPOL",
            label="Annopol (mojż.)",
            par_id="74a",
            url="https://regestry.lubgens.eu/viewpage.php?page_id=1052&par=74a",
        ),
    ]


def test_parse_parish_links_requires_navigation_section() -> None:
    module = load_script_module()

    try:
        module.parse_parish_links("<html></html>")
    except ValueError as exc:
        assert "#navigation" in str(exc)
    else:
        raise AssertionError("parse_parish_links should reject pages without #navigation")


def test_fetch_page_verbose_prints_url(capsys) -> None:
    module = load_script_module()

    class Response:
        text = "<html></html>"

        def raise_for_status(self) -> None:
            pass

    class Session:
        def get(self, url: str, timeout: float) -> Response:
            assert url == "https://regestry.lubgens.eu/news.php"
            assert timeout == 30.0
            return Response()

    assert (
        module.fetch_page(
            Session(),
            "https://regestry.lubgens.eu/news.php",
            30.0,
            verbose=True,
        )
        == "<html></html>"
    )

    captured = capsys.readouterr()
    assert captured.err == "Fetching https://regestry.lubgens.eu/news.php\n"


def test_parse_parish_name_uses_name_after_place_comma() -> None:
    module = load_script_module()
    html = """
    <div class="mainbox">
      <div class="par">Abramowice, św. Jakuba Apostoła</div>
    </div>
    """

    assert module.parse_parish_name(html, fallback="Abramowice") == "św. Jakuba Apostoła"


def test_parse_decades_extracts_categories() -> None:
    module = load_script_module()
    html = """
    <div class="mainbox">
      <div id="decsboxz"><span id="z188">1880 - 1889</span></div>
      <div id="decsboxs"><span id="s190">1900 - 1909</span></div>
      <div id="decsboxu"><span id="u176">1760 - 1769</span><span id="u178">1780 - 1789</span></div>
    </div>
    """

    assert module.parse_decades(html) == {
        "u": ["176", "178"],
        "s": ["190"],
        "z": ["188"],
    }


def test_parse_years_from_index_html_uses_rok_column() -> None:
    module = load_script_module()
    html = """
    <table class="indtbl">
      <tr><th>NAZWISKO</th><th>AKT</th><th>ROK</th><th>UWAGI</th></tr>
      <tr><td>Kowalski</td><td>1</td><td>1812</td><td></td></tr>
      <tr><td>Nowak</td><td>2</td><td>1819</td><td></td></tr>
      <tr><td>Malformed</td><td>3</td><td>brak</td><td></td></tr>
    </table>
    """

    assert module.parse_years_from_index_html(html) == [1812, 1819]
