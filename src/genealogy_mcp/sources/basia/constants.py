"""Static config for the BaSIA source.

BaSIA ("Baza Systemu Indeksacji Archiwalnej", https://basia.famula.pl) is
the WTG-Gniazdo / PSNC index of archival vital records and other documents
from Wielkopolska (Greater Poland), 18th-20th c. (with some older entries).
The corpus is large (6.6M+ entries) and the search is a fuzzy name match
that runs server-side over the whole base, so it is **slow**: a bare
surname can take 80s+, and a query broad enough to time out server-side
comes back as a truncated HTML page. Narrowing with a given name, a year
range, a place, a record type, or a higher similarity threshold makes the
search both faster and more useful.

The search form (both the simple ``q`` box and the "Wyszukiwanie
rozszerzone" advanced form) POSTs to ``/``. We always drive the advanced
form because it is a superset: a single person (``*0`` fields), an
inclusive year range, an optional place + radius, and optional document /
unit type filters. The toggle hidden inputs (``showtype`` / ``showplaces``
/ ``showdate``) gate whether the matching filters are honoured, so we only
flip them to ``block`` when the caller supplies that filter.
"""

from __future__ import annotations

DEFAULT_BASE_URL = "https://basia.famula.pl"
SEARCH_PATH = "/"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_MIN_INTERVAL_SECONDS = 5.0
# The search is slow; broad queries legitimately take well over a minute.
DEFAULT_TIMEOUT_SECONDS = 200.0

# The advanced form's effective default fuzzy-match floor; records scoring
# below this similarity are excluded. Higher = stricter (fewer, closer
# matches) and faster; lower = broader and slower.
DEFAULT_SIMILARITY = 60

# The year slider's bounds on the upstream form.
YEAR_MIN = 1577

# Form-value maps. Keys are the friendly argument values; values are the
# raw codes the upstream form expects.
SEX_TO_FORM: dict[str, str] = {"any": "any", "male": "m", "female": "k"}

# type0 — the indexed person's relation to the document. The upstream
# groups spouse and parent under one option ("Małżonek/Rodzic").
RELATION_TO_FORM: dict[str, str] = {
    "any": "any",
    "parent_or_spouse": "parent",
    "child": "child",
    "other": "other",
}

# type_record — kind of document.
RECORD_TYPE_TO_FORM: dict[str, str] = {
    "any": "any",
    "birth": "a",  # Akt urodzenia/chrztu
    "marriage": "b",  # Akt małżeństwa
    "death": "c",  # Akt zgonu
    "banns": "d",  # Zapowiedzi
    "other": "z",  # Inny
}

# type_unit — kind of records-keeping unit.
UNIT_TYPE_TO_FORM: dict[str, str] = {
    "any": "any",
    "usc": "usc",  # Urząd Stanu Cywilnego (civil registry)
    "catholic": "kat",  # Parafia rzymskokatolicka
    "evangelical": "ewa",  # Parafia ewangelicka
    "other": "other",
}

# Result-box CSS class suffix -> record type. The upstream tags every box
# ``result_box usc<x>`` regardless of unit kind; the trailing letter is the
# meaningful part. Banns/other share the ``other`` class and are told apart
# by the record-type label phrase (see parser).
CLASS_TO_RECORD_TYPE: dict[str, str] = {
    "usca": "birth",
    "uscb": "marriage",
    "uscc": "death",
}
