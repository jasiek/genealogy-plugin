"""Static catalogues for the genbaza source.

A handful of regional Polish genealogy societies publish indexed vital
records through near-identical PHP frontends hosted under ``*.genbaza.pl``.
They all expose a single AJAX endpoint ``/php/getdata.php`` accepting the
same set of GET parameters and returning an HTML fragment. Two row layouts
exist in the wild:

* **Variant A** (swietogen, warmia, pomerania): per-record-type table
  (births / marriages / deaths) with 10 columns including ``Akt/Strona``,
  ``Rok``, ``USC/Parafia``.
* **Variant B** (polishgenealogy, kurpie): one combined table with 7
  columns; the year and other facts live as ``key: value`` items inside
  the ``Inne informacje`` cell.

The union query string accepted by both is:

    ?im=&naz=&miejsc=&rok1=&rok2=&inne=&malz=&naz_malz=&ojc=&mat=
    &naz_mat=&pag=&sort1=&sort2=&sort3=&metr=&dokl=&metod=&rodz=&zasob=
"""

SITES: dict[str, str] = {
    "swietogen": "https://swietogen.genbaza.pl",
    "polishgenealogy": "https://polishgenealogy.genbaza.pl",
    "warmia": "https://warmia.genbaza.pl",
    "kurpie": "https://kurpie.genbaza.pl",
    "pomerania": "https://pomerania.genbaza.pl",
}

ENDPOINT_PATH = "/php/getdata.php"

# `rodz` query parameter values for variant-A sites; variant B ignores
# this and returns one combined table regardless.
RECORD_TYPE_TO_RODZ: dict[str, int] = {"birth": 1, "death": 2, "marriage": 3}
RODZ_TO_RECORD_TYPE: dict[int, str] = {v: k for k, v in RECORD_TYPE_TO_RODZ.items()}

# The upstream JS calls this `pl2uni`: substitutes Polish diacritics with
# fixed ``xNNN`` tokens before sending the query string. Server-side the
# tokens are reversed back to the diacritic. The numeric suffixes are not
# Unicode codepoints — they are an in-house mapping baked into the PHP.
PL2UNI: dict[str, str] = {
    "Ą": "x260",
    "Ć": "x262",
    "Ę": "x280",
    "Ł": "x321",
    "Ń": "x323",
    "Ó": "x211",
    "Ś": "x346",
    "Ź": "x377",
    "Ż": "x379",
    "ą": "x261",
    "ć": "x263",
    "ę": "x281",
    "ł": "x322",
    "ń": "x324",
    "ó": "x243",
    "ś": "x347",
    "ż": "x380",
    "ź": "x378",
}

# Same default cadence as the other research sources. The genbaza sites
# are small community-run servers — be polite.
DEFAULT_MIN_INTERVAL_SECONDS = 5.0

# These PHP frontends gate non-empty responses on an ``agree=1`` cookie
# (the cookie-consent banner sets it client-side).
DEFAULT_COOKIES: dict[str, str] = {"agree": "1"}

# Browser-style UA. The upstream doesn't appear to UA-sniff but other
# sources in this repo (geneteka) get 403'd on bot UAs, so play it safe.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
