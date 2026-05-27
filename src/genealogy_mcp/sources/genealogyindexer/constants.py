"""Static config for the Genealogy Indexer source.

Genealogy Indexer (https://genealogyindexer.org) is Logan Kleinwaks'
full-text search engine over digitised historical *directories* (business,
address, telephone, lawyer, voter, etc.), *yizkor* (Holocaust memorial)
books, *military* lists, community/personal *history* books, and *school*
sources from Central and Eastern Europe and beyond. It is OCR full text,
not a structured index, so it complements the parish/vital-record sources:
a surname turns up wherever it was printed (a directory listing, a memorial
roll), with a snippet of context and a link to the scanned page.

The single search form POSTs ``application/x-www-form-urlencoded`` to ``/``.
Searches are full text over the OCR'd page text and support the upstream
query operators (phrase, wildcard, OR ``|``, AND, NOT ``-``, proximity
``~N``, forced-Soundex ``[s]``, per-source ``{d82}`` and date ``{1903-1923}``
filters) verbatim inside ``term``.
"""

from __future__ import annotations

import re

DEFAULT_BASE_URL = "https://genealogyindexer.org"
SEARCH_PATH = "/"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_MIN_INTERVAL_SECONDS = 5.0
# A result page for a common surname can run to several megabytes, so give
# the transfer a generous ceiling even though the search itself is fast.
DEFAULT_TIMEOUT_SECONDS = 90.0

# The upstream lists every match it finds but caps how many it renders for
# very common terms; we additionally cap returned items here by default.
DEFAULT_MAX_RESULTS = 100

# Form-value maps. Keys are the friendly argument values; values are the
# raw codes the ``match`` / ``sort`` / ``collection`` / ``date`` /
# ``transliteration`` selects on the upstream form expect.
MATCH_TO_FORM: dict[str, str] = {
    "regular": "regular",
    "soundex": "dm",  # Daitch-Mokotoff Soundex — spelling variants
    "ocr": "ocr",  # OCR-adjusted, tolerant of scanning errors
}

SORT_TO_FORM: dict[str, str] = {
    "regular": "dist",
    "newest": "newness",  # newly indexed sources first
    "alphabetic": "alpha",
}

COLLECTION_TO_FORM: dict[str, str] = {
    "any": "any",
    "directories": "directories",
    "yizkor": "yizkor",
    "military": "military",
    "history": "history",
    "school": "school",
}

DATE_TO_FORM: dict[str, str] = {
    "any": "any",
    "to_1918": "1918",  # –1918
    "1919_1945": "1945",  # 1919–1945
    "from_1946": "1946",  # 1946–
}

TRANSLITERATION_TO_FORM: dict[str, str] = {
    "none": "none",
    "add_cyrillic": "addcyr",  # the site's own default
    "add_cyrillic_hebrew": "addall",
    "add_hebrew": "addheb",
    "only_cyrillic": "onlycyr",
    "only_cyrillic_hebrew": "onlyall",
    "only_hebrew": "onlyheb",
}

# Country / top-level scope codes from the form's "Place" dropdown. Sub-region
# and city codes (e.g. Kraków, Lwów, the gubernias) are omitted to keep this
# unambiguous — pass them as a raw code string instead (they match
# ``SCOPE_CODE_RE``). "Galicia"/"Silesia"/"Bessarabia" map to the
# multinational (cross-border) entries.
PLACE_TO_SCOPE: dict[str, str] = {
    "argentina": "37000",
    "austria": "14000",
    "belarus": "20000",
    "belgium": "34000",
    "bessarabia": "+24000",
    "bosnia and herzegovina": "42000",
    "bulgaria": "7000",
    "china": "13000",
    "costa rica": "38000",
    "croatia": "35000",
    "cuba": "29000",
    "czech": "11000",
    "denmark": "30000",
    "egypt": "25000",
    "estonia and latvia": "+15000",
    "france": "8000",
    "galicia": "+1100",
    "germany": "160000",
    "honduras": "39000",
    "hungary": "9000",
    "israel": "10000",
    "italy": "43000",
    "latvia and estonia": "15000",
    "lithuania": "5000",
    "mexico": "22000",
    "moldova": "24000",
    "netherlands": "6000",
    "north macedonia": "41000",
    "oceania": "23000",
    "philippines": "40000",
    "poland": "1000",
    "romania": "2000",
    "russia": "12000",
    "serbia": "36000",
    "silesia": "+1200",
    "slovakia": "31000",
    "slovenia": "32000",
    "south africa": "28000",
    "suriname": "33000",
    "switzerland": "18000",
    "thailand": "26000",
    "ukraine": "19000",
    "united kingdom": "4000",
    "united states": "21000",
    "uzbekistan": "27000",
}

# A raw scope code, as it appears as an <option value> on the form: an
# optional leading "+" (multinational) or single region-prefix letter, then
# digits. e.g. "1000", "+1100", "b5300", "h31001", "u1102", "p20100".
SCOPE_CODE_RE = re.compile(r"^\+?[a-z]?\d+$")
