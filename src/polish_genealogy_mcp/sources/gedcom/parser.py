"""Parse a GEDCOM file into in-memory dicts using ged4py.

`load(path)` returns a `GedcomStore` with persons / families / sources / events
indexed by xref id. Events get synthetic ids of the form
``<owner_xref>:<TAG>[#<n>]`` so they can be addressed individually.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ged4py.parser import GedcomReader

# GEDCOM event tags we surface. The first two are first-class life events;
# the rest are individual or family events that show up frequently in
# Polish-genealogy GEDCOMs.
PERSON_EVENT_TAGS: tuple[str, ...] = (
    "BIRT",
    "CHR",
    "BAPM",
    "DEAT",
    "BURI",
    "CREM",
    "RESI",
    "OCCU",
    "EDUC",
    "EMIG",
    "IMMI",
    "NATU",
    "CENS",
    "EVEN",
)
FAMILY_EVENT_TAGS: tuple[str, ...] = (
    "MARR",
    "DIV",
    "ENGA",
    "MARB",
    "MARC",
    "ANUL",
    "EVEN",
)
BIRTH_TAGS = {"BIRT", "CHR", "BAPM"}
DEATH_TAGS = {"DEAT", "BURI", "CREM"}

_YEAR_RE = re.compile(r"\b(\d{3,4})\b")


def fold(s: str | None) -> str:
    """Lowercase + strip diacritics for forgiving substring matching."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _extract_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    m = _YEAR_RE.search(date_str)
    return int(m.group(1)) if m else None


@dataclass
class Place:
    id: str
    name: str


@dataclass
class Event:
    id: str
    tag: str
    date: str | None
    year: int | None
    place: Place | None
    title: str | None
    owner_id: str | None
    cause: str | None = None
    age: str | None = None
    notes: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    participants: list[dict] = field(default_factory=list)


@dataclass
class Person:
    id: str
    surname: str
    given_names: str
    sex: str | None
    nickname: str | None
    title: str | None
    occupation: str | None
    father_id: str | None
    mother_id: str | None
    family_child_id: str | None
    family_spouse_ids: list[str]
    event_ids: list[str]
    notes: list[str]
    source_ids: list[str]
    birth_id: str | None
    death_id: str | None


@dataclass
class Family:
    id: str
    husband_id: str | None
    wife_id: str | None
    children_ids: list[str]
    event_ids: list[str]
    marriage_id: str | None


@dataclass
class Source:
    id: str
    title: str | None
    author: str | None
    publication: str | None
    abbreviation: str | None
    text: str | None
    repository_id: str | None
    repository_title: str | None


@dataclass
class GedcomStore:
    path: Path
    persons: dict[str, Person] = field(default_factory=dict)
    families: dict[str, Family] = field(default_factory=dict)
    events: dict[str, Event] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    repositories: dict[str, str] = field(default_factory=dict)
    places: dict[str, Place] = field(default_factory=dict)


def _value(rec, tag: str) -> str | None:
    """Return the literal string value of the first sub-tag named `tag`.

    `Record.sub_tag()` auto-dereferences pointers (turning ``FAMC @F1@``
    into the FAM record itself), which loses the xref. Iterate raw
    `sub_records` so we can read pointer values verbatim.
    """
    for sub in rec.sub_records:
        if sub.tag == tag:
            v = sub.value
            if isinstance(v, str) and v:
                return v
            return None
    return None


def _values(rec, tag: str) -> list[str]:
    out: list[str] = []
    for sub in rec.sub_records:
        if sub.tag == tag and isinstance(sub.value, str) and sub.value:
            out.append(sub.value)
    return out


def _sub_tag_value(sub, tag: str) -> str | None:
    for s in sub.sub_records:
        if s.tag == tag:
            v = s.value
            if isinstance(v, str):
                return v or None
            if v is None:
                return None
            # ged4py wraps DATE in a DateValue object; fall back to str().
            text = str(v)
            return text or None
    return None


def _sub_tag_values(sub, tag: str) -> list[str]:
    return [
        s.value for s in sub.sub_records if s.tag == tag and isinstance(s.value, str) and s.value
    ]


def _make_event(
    store: GedcomStore,
    sub,
    owner_id: str,
    tag: str,
    seq: int,
) -> str:
    eid = f"{owner_id}:{tag}" if seq == 0 else f"{owner_id}:{tag}#{seq}"
    date = _sub_tag_value(sub, "DATE")
    plac = _sub_tag_value(sub, "PLAC")
    place = None
    if plac:
        if plac not in store.places:
            store.places[plac] = Place(id=plac, name=plac)
        place = store.places[plac]
    title = sub.value if (isinstance(sub.value, str) and sub.value and tag == "EVEN") else None

    notes = _sub_tag_values(sub, "NOTE")
    source_ids = [v for v in _sub_tag_values(sub, "SOUR") if v.startswith("@") and v.endswith("@")]

    ev = Event(
        id=eid,
        tag=tag,
        date=date,
        year=_extract_year(date),
        place=place,
        title=title,
        owner_id=owner_id,
        cause=_sub_tag_value(sub, "CAUS"),
        age=_sub_tag_value(sub, "AGE"),
        notes=notes,
        source_ids=source_ids,
    )
    store.events[eid] = ev
    return eid


def _read_person(store: GedcomStore, rec) -> Person:
    name = rec.name
    surname = (name.surname if name else "") or ""
    given = (name.first if name else "") or ""

    sex_raw = rec.sex
    sex = sex_raw if sex_raw in ("M", "F") else ("U" if sex_raw else None)

    famc = _value(rec, "FAMC")
    famss = _values(rec, "FAMS")

    event_ids: list[str] = []
    seen_tag_counts: dict[str, int] = {}
    birth_id: str | None = None
    death_id: str | None = None
    for sub in rec.sub_records:
        tag = sub.tag
        if tag not in PERSON_EVENT_TAGS:
            continue
        seq = seen_tag_counts.get(tag, 0)
        seen_tag_counts[tag] = seq + 1
        eid = _make_event(store, sub, rec.xref_id, tag, seq)
        event_ids.append(eid)
        if birth_id is None and tag in BIRTH_TAGS:
            birth_id = eid
        if death_id is None and tag in DEATH_TAGS:
            death_id = eid

    return Person(
        id=rec.xref_id,
        surname=surname,
        given_names=given,
        sex=sex,
        nickname=_value(rec, "NICK"),
        title=_value(rec, "TITL"),
        occupation=_value(rec, "OCCU"),
        father_id=None,  # filled in after families are read
        mother_id=None,
        family_child_id=famc,
        family_spouse_ids=famss,
        event_ids=event_ids,
        notes=_values(rec, "NOTE"),
        source_ids=[v for v in _values(rec, "SOUR") if v.startswith("@") and v.endswith("@")],
        birth_id=birth_id,
        death_id=death_id,
    )


def _read_family(store: GedcomStore, rec) -> Family:
    husb = _value(rec, "HUSB")
    wife = _value(rec, "WIFE")
    children = _values(rec, "CHIL")
    event_ids: list[str] = []
    marriage_id: str | None = None
    seen: dict[str, int] = {}
    for sub in rec.sub_records:
        tag = sub.tag
        if tag not in FAMILY_EVENT_TAGS:
            continue
        seq = seen.get(tag, 0)
        seen[tag] = seq + 1
        eid = _make_event(store, sub, rec.xref_id, tag, seq)
        event_ids.append(eid)
        if marriage_id is None and tag == "MARR":
            marriage_id = eid
    return Family(
        id=rec.xref_id,
        husband_id=husb,
        wife_id=wife,
        children_ids=children,
        event_ids=event_ids,
        marriage_id=marriage_id,
    )


def _read_source(rec) -> Source:
    repo_id = _value(rec, "REPO")
    return Source(
        id=rec.xref_id,
        title=_value(rec, "TITL"),
        author=_value(rec, "AUTH"),
        publication=_value(rec, "PUBL"),
        abbreviation=_value(rec, "ABBR"),
        text=_value(rec, "TEXT"),
        repository_id=repo_id,
        repository_title=None,  # resolved post-pass
    )


def load(path: Path | str) -> GedcomStore:
    """Read a GEDCOM file fully into memory and return a `GedcomStore`."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"GEDCOM file not found: {path}")

    store = GedcomStore(path=path)

    with GedcomReader(str(path)) as reader:
        for rec in reader.records0("INDI"):
            p = _read_person(store, rec)
            store.persons[p.id] = p
        for rec in reader.records0("FAM"):
            f = _read_family(store, rec)
            store.families[f.id] = f
        for rec in reader.records0("SOUR"):
            s = _read_source(rec)
            store.sources[s.id] = s
        for rec in reader.records0("REPO"):
            store.repositories[rec.xref_id] = _value(rec, "NAME") or rec.xref_id

    # Resolve parent ids from family records.
    for person in store.persons.values():
        if person.family_child_id:
            fam = store.families.get(person.family_child_id)
            if fam:
                person.father_id = fam.husband_id
                person.mother_id = fam.wife_id

    # Resolve repository titles on sources.
    for src in store.sources.values():
        if src.repository_id:
            src.repository_title = store.repositories.get(src.repository_id)

    return store
