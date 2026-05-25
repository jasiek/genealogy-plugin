"""Parse a BaSIA search-results page into typed records.

The upstream returns a full HTML document. Each hit is a
``<div class='result_box usc<x>' id='resboxid<ID>'>`` holding two columns:

* ``.lbox`` — place (a ``unit_info.php`` link), a header line
  ``(<unit type>) - <record kind>, rok <year> , <book title>``, the
  principal person (in ``<b>``, optionally followed by an age), their
  ``rodzice:`` (parents), a ``małżonek`` (spouse), a fuzzy-match score in a
  ``progress-container`` div, and optional ``Inne osoby …`` (other people)
  and ``Komentarz indeksującego`` (indexer comment) sections.
* ``.rbox`` — the holding archive (a ``showbox.php`` link), a scan link
  (signature + ``skan N``, pointing at szukajwarchiwach / familysearch),
  the indexer, the date added, the numeric ID, and a ``/record/…``
  permalink.

Result boxes are deeply nested, so we split them with BeautifulSoup; the
per-field extraction inside each box is positional (anchored on the Polish
marker words ``rodzice:`` / ``małżonek`` / ``Inne osoby`` / ``Komentarz``),
which survives the markup quirks better than one big regex.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from genealogy_mcp.sources.basia.constants import CLASS_TO_RECORD_TYPE
from genealogy_mcp.sources.basia.models import BasiaRecord, BasiaSearchResult, RecordType

# Anchors the page must contain once a search has actually executed; their
# absence means either a truncated response or a changed page structure.
_SEARCH_RAN_RE = re.compile(r"Czas\s+wyszukiwania", re.IGNORECASE)
_SEARCH_TIME_RE = re.compile(r"Czas\s+wyszukiwania:\s*([\d.]+)\s*s", re.IGNORECASE)

_RESBOXID_RE = re.compile(r"resboxid(\d+)")
_AGE_RE = re.compile(r"\((\d+\s*l(?:at|ata)?)\)")
_DATE_ADDED_RE = re.compile(r"dodano:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")

# Sentinels wrapped around <b> runs so the principal person, the spouse,
# and the section labels survive flattening as locatable markers.
_BOLD_OPEN = "\x01"
_BOLD_CLOSE = "\x02"
_BOLD_RE = re.compile(_BOLD_OPEN + r"(.*?)" + _BOLD_CLOSE, re.DOTALL)

# A header reads "(unit) - <kind>, rok <year> , <book>" for vital records,
# or the terser "<kind> <year> , <book>" (no parens, no "rok") for the
# catch-all "inne" / banns entries.
_HEADER_UNIT_RE = re.compile(r"\(([^)]*)\)\s*-?\s*")
_HEADER_ROK_RE = re.compile(r"^(.*?),\s*rok\s*(\d{3,4})\b\s*(?:,\s*(.*))?$", re.DOTALL)
_HEADER_BARE_RE = re.compile(r"^(.*?)\s+(\d{3,4})\b\s*(?:,\s*(.*))?$", re.DOTALL)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(_BOLD_OPEN, " ").replace(_BOLD_CLOSE, " ")).strip()


def _record_type(box: Tag, label: str | None) -> RecordType:
    classes = box.get("class") or []
    for cls in classes:
        rt = CLASS_TO_RECORD_TYPE.get(cls)
        if rt:
            return rt  # type: ignore[return-value]
    # Births/marriages/deaths are tagged via class; everything else lands in
    # the catch-all ``other`` class. Tell banns apart by the label phrase.
    if label and "zapowied" in label.lower():
        return "banns"
    return "other"


def _split_name(full: str | None) -> tuple[str | None, str | None]:
    """Best-effort split of an indexed full name into (given, surname)."""
    if not full:
        return None, None
    parts = full.split(None, 1)
    if len(parts) == 1:
        return parts[0] or None, None
    return parts[0] or None, parts[1].strip() or None


def _split_parents(raw: str) -> tuple[str | None, str | None]:
    raw = raw.strip().strip(",").strip()
    if not raw:
        return None, None
    bits = [b.strip() for b in raw.split(",") if b.strip()]
    father = bits[0] if bits else None
    mother = bits[1] if len(bits) > 1 else None
    return father or None, mother or None


def _parse_header(header: str, out: dict[str, object]) -> None:
    rest = header.strip()
    um = _HEADER_UNIT_RE.match(rest)
    if um:
        out["unit_type"] = (um.group(1) or "").strip() or None
        rest = rest[um.end() :]
    m = _HEADER_ROK_RE.match(rest) or _HEADER_BARE_RE.match(rest)
    if m:
        out["record_type_label"] = (m.group(1) or "").strip() or None
        out["year"] = int(m.group(2))
        out["book_title"] = (m.group(3) or "").strip() or None
    else:
        label = rest.strip().strip(",").strip()
        out["record_type_label"] = label or None


def _is_label(text: str) -> bool:
    return text.startswith("Inne osoby") or text.startswith("Komentarz")


def _parse_lbox(lbox: Tag) -> dict[str, object]:
    out: dict[str, object] = {}

    # Similarity, then drop the widget so it stops splitting the text it is
    # embedded inside.
    pc = lbox.find("div", class_="progress-container")
    if isinstance(pc, Tag):
        m = re.search(r"(\d+)\s*%", pc.get("title", "") or "")
        if m:
            out["similarity"] = int(m.group(1))
        pc.decompose()

    # Place + its unit, then drop the heading span so the header text that
    # follows starts cleanly.
    place_a = lbox.find("a", href=re.compile(r"unit_info\.php"))
    if isinstance(place_a, Tag):
        out["place"] = place_a.get_text(" ", strip=True) or None
        heading = place_a.find_parent("span") or place_a
        heading.extract()

    # Wrap bold runs (person names + the section labels) in sentinels so
    # they stay locatable after flattening, then turn <br> into newlines.
    for b in lbox.find_all("b"):
        b.replace_with(_BOLD_OPEN + b.get_text(" ", strip=True) + _BOLD_CLOSE)
    for br in lbox.find_all("br"):
        br.replace_with("\n")
    text = lbox.get_text("")

    first_bold = text.find(_BOLD_OPEN)
    header = text if first_bold == -1 else text[:first_bold]
    body = "" if first_bold == -1 else text[first_bold:]
    _parse_header(header, out)

    bolds = [(m.start(), m.end(), m.group(1).strip()) for m in _BOLD_RE.finditer(body)]
    label_starts = [s for (s, _e, t) in bolds if _is_label(t)]
    region_end = min(label_starts) if label_starts else len(body)
    persons = [(s, e, t) for (s, e, t) in bolds if s < region_end and not _is_label(t)]

    if persons:
        p0s, p0e, p0t = persons[0]
        if p0t:
            out["name"] = p0t
            given, surname = _split_name(p0t)
            out["given_name"] = given
            out["surname"] = surname
        # Everything between the principal's name and the next person (or the
        # start of the labels section) is their age + parents.
        next_start = persons[1][0] if len(persons) > 1 else region_end
        tail = body[p0e:next_start]
        age_m = _AGE_RE.search(tail)
        if age_m:
            out["age"] = re.sub(r"\s+", " ", age_m.group(1)).strip()
        pm = re.search(r"rodzice:\s*(.*?)\s*(?:\n*małżonek|$)", tail, re.DOTALL)
        if pm:
            parents_raw = _norm(pm.group(1)).strip(",").strip()
            if parents_raw:
                out["parents_raw"] = parents_raw
                father, mother = _split_parents(parents_raw)
                out["father"] = father
                out["mother"] = mother
        # The second named person is the spouse (a marriage's other party, or
        # a death/birth act's "małżonek").
        if len(persons) > 1 and persons[1][2]:
            out["spouse"] = persons[1][2]

    # Other people named in the document, then the indexer comment.
    inne_end = next((e for (_s, e, t) in bolds if t.startswith("Inne osoby")), None)
    kom = next(((s, e) for (s, e, t) in bolds if t.startswith("Komentarz")), None)
    if inne_end is not None:
        seg = body[inne_end : (kom[0] if kom else len(body))].lstrip(": \n")
        others = [_norm(ln) for ln in seg.split("\n") if ln.strip()]
        out["other_persons"] = [o for o in others if o]
    if kom is not None:
        comment = _norm(body[kom[1] :].lstrip(": \n"))
        out["indexer_comment"] = comment or None

    return out


def _parse_rbox(rbox: Tag) -> dict[str, object]:
    out: dict[str, object] = {}

    archive_a = rbox.find("a", href=re.compile(r"showbox\.php"))
    if isinstance(archive_a, Tag):
        out["archive"] = archive_a.get_text(" ", strip=True) or None

    # The scan link is the external (target=_blank) anchor whose text names a
    # scan ("…, skan N"); its href is the digitised-image URL.
    for a in rbox.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if "skan" in label.lower():
            out["scan_url"] = a["href"]
            out["scan_label"] = label or None
            m = re.match(r"(.*?),\s*skan", label)
            if m:
                out["signature"] = m.group(1).strip() or None
            break

    indexer_a = rbox.find("a", href=re.compile(r"/profile/\d+"))
    if isinstance(indexer_a, Tag):
        out["indexer"] = indexer_a.get_text(" ", strip=True) or None

    perma_a = rbox.find("a", href=re.compile(r"^/record/"))
    if isinstance(perma_a, Tag):
        out["permalink"] = perma_a["href"]

    dm = _DATE_ADDED_RE.search(rbox.get_text(" "))
    if dm:
        out["date_added"] = dm.group(1)

    return out


def _parse_box(box: Tag) -> BasiaRecord:
    fields: dict[str, object] = {}

    rid = box.get("id") or ""
    m = _RESBOXID_RE.search(rid)
    if m:
        fields["record_id"] = m.group(1)

    lbox = box.find("div", class_="lbox")
    if isinstance(lbox, Tag):
        fields.update(_parse_lbox(lbox))

    rbox = box.find("div", class_="rbox")
    if isinstance(rbox, Tag):
        fields.update(_parse_rbox(rbox))

    fields["record_type"] = _record_type(box, fields.get("record_type_label"))  # type: ignore[arg-type]
    return BasiaRecord(**fields)  # type: ignore[arg-type]


def parse_search_response(
    body: str,
    *,
    surname_query: str | None = None,
    given_name_query: str | None = None,
    base_url: str = "https://basia.famula.pl",
    max_results: int | None = None,
) -> BasiaSearchResult:
    """Parse a BaSIA results page.

    Raises ``ValueError`` if the page shows no sign a search executed —
    which on this upstream means a server-side timeout truncated the
    response (common for broad queries) or the page layout changed. A
    genuinely empty result set (search ran, zero hits) returns an empty
    ``items`` list.
    """
    if not _SEARCH_RAN_RE.search(body):
        raise ValueError(
            "BaSIA response carries no search marker ('Czas wyszukiwania'); "
            "the query likely timed out server-side and returned a truncated "
            "page. Narrow it (given name, year range, place, record type, or "
            "a higher similarity) and retry."
        )

    search_time: float | None = None
    tm = _SEARCH_TIME_RE.search(body)
    if tm:
        try:
            search_time = float(tm.group(1))
        except ValueError:
            search_time = None

    soup = BeautifulSoup(body, "html.parser")
    boxes = soup.find_all("div", class_="result_box")

    records: list[BasiaRecord] = []
    for box in boxes:
        if isinstance(box, Tag):
            rec = _parse_box(box)
            if rec.permalink and rec.permalink.startswith("/"):
                rec.permalink = base_url.rstrip("/") + rec.permalink
            records.append(rec)

    total = len(records)
    truncated = False
    if max_results is not None and total > max_results:
        records = records[:max_results]
        truncated = True

    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.record_type] = counts.get(rec.record_type, 0) + 1

    return BasiaSearchResult(
        surname_query=surname_query,
        given_name_query=given_name_query,
        counts=counts,
        total=total,
        truncated=truncated,
        search_time_seconds=search_time,
        items=records,
    )
