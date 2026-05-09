"""In-memory query layer over a `GedcomStore`."""

from __future__ import annotations

from polish_genealogy_mcp.sources.gedcom.models import (
    EventDetail,
    EventSearchResult,
    EventSummary,
    FamilyView,
    PersonDetail,
    PersonSearchResult,
    PersonSummary,
    PlaceRef,
    PlaceSearchResult,
    SourceSearchResult,
    SourceSummary,
    UnionSummary,
)
from polish_genealogy_mcp.sources.gedcom.parser import (
    BIRTH_TAGS,
    DEATH_TAGS,
    Event,
    GedcomStore,
    Person,
    fold,
)


def _place_to_model(p) -> PlaceRef | None:
    if p is None:
        return None
    return PlaceRef(id=p.id, name=p.name)


def _event_to_summary(ev: Event | None) -> EventSummary | None:
    if ev is None:
        return None
    return EventSummary(
        id=ev.id,
        tag=ev.tag,
        date=ev.date,
        year=ev.year,
        place=_place_to_model(ev.place),
        title=ev.title,
        owner_id=ev.owner_id,
    )


def _person_to_summary(store: GedcomStore, p: Person) -> PersonSummary:
    birth = store.events.get(p.birth_id) if p.birth_id else None
    death = store.events.get(p.death_id) if p.death_id else None
    return PersonSummary(
        id=p.id,
        surname=p.surname,
        given_names=p.given_names,
        sex=p.sex,
        birth=_event_to_summary(birth),
        death=_event_to_summary(death),
    )


def _person_event_in_place(store: GedcomStore, p: Person, folded_place: str) -> bool:
    for eid in p.event_ids:
        ev = store.events.get(eid)
        if ev and ev.place and folded_place in fold(ev.place.name):
            return True
    return False


def _person_event_in_year_range(
    store: GedcomStore,
    p: Person,
    tags: set[str],
    after: int | None,
    before: int | None,
) -> bool:
    for eid in p.event_ids:
        ev = store.events.get(eid)
        if not ev or ev.tag not in tags or ev.year is None:
            continue
        if after is not None and ev.year < after:
            continue
        if before is not None and ev.year > before:
            continue
        return True
    return False


def search_persons(
    store: GedcomStore,
    *,
    name: str | None = None,
    surname: str | None = None,
    given_name: str | None = None,
    sex: str | None = None,
    born_after: int | None = None,
    born_before: int | None = None,
    died_after: int | None = None,
    died_before: int | None = None,
    place: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PersonSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    fname = fold(name)
    fsurname = fold(surname)
    fgiven = fold(given_name)
    fplace = fold(place)
    sex_norm = sex.upper() if sex else None

    matches: list[Person] = []
    for p in store.persons.values():
        if fsurname and fsurname not in fold(p.surname):
            continue
        if fgiven and fgiven not in fold(p.given_names):
            continue
        if fname and fname not in fold(p.surname) and fname not in fold(p.given_names):
            continue
        if sex_norm and (p.sex or "") != sex_norm:
            continue
        if (born_after is not None or born_before is not None) and not _person_event_in_year_range(
            store, p, BIRTH_TAGS, born_after, born_before
        ):
            continue
        if (died_after is not None or died_before is not None) and not _person_event_in_year_range(
            store, p, DEATH_TAGS, died_after, died_before
        ):
            continue
        if fplace and not _person_event_in_place(store, p, fplace):
            continue
        matches.append(p)

    matches.sort(key=lambda p: (fold(p.surname), fold(p.given_names), p.id))
    total = len(matches)
    page = matches[offset : offset + limit]
    return PersonSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        items=[_person_to_summary(store, p) for p in page],
    )


def get_person(store: GedcomStore, person_id: str) -> PersonDetail | None:
    p = store.persons.get(person_id)
    if p is None:
        return None
    base = _person_to_summary(store, p)
    events = [_event_to_summary(store.events[eid]) for eid in p.event_ids if eid in store.events]
    unions = [u for u in (_load_union(store, fid) for fid in p.family_spouse_ids) if u is not None]
    n_children = sum(len(u.children_ids) for u in unions)
    return PersonDetail(
        **base.model_dump(),
        nickname=p.nickname,
        title=p.title,
        occupation=p.occupation,
        father_id=p.father_id,
        mother_id=p.mother_id,
        family_child_id=p.family_child_id,
        n_unions=len(unions),
        n_children=n_children,
        events=events,
        unions=unions,
        notes=p.notes,
        source_ids=p.source_ids,
    )


def _load_union(store: GedcomStore, family_id: str) -> UnionSummary | None:
    fam = store.families.get(family_id)
    if fam is None:
        return None
    marriage = store.events.get(fam.marriage_id) if fam.marriage_id else None
    return UnionSummary(
        id=fam.id,
        husband_id=fam.husband_id,
        wife_id=fam.wife_id,
        marriage=_event_to_summary(marriage),
        children_ids=list(fam.children_ids),
    )


def get_family(store: GedcomStore, person_id: str) -> FamilyView | None:
    p = store.persons.get(person_id)
    if p is None:
        return None
    person = _person_to_summary(store, p)

    father = mother = None
    if p.father_id and p.father_id in store.persons:
        father = _person_to_summary(store, store.persons[p.father_id])
    if p.mother_id and p.mother_id in store.persons:
        mother = _person_to_summary(store, store.persons[p.mother_id])

    siblings: list[PersonSummary] = []
    if p.family_child_id and p.family_child_id in store.families:
        for cid in store.families[p.family_child_id].children_ids:
            if cid != p.id and cid in store.persons:
                siblings.append(_person_to_summary(store, store.persons[cid]))

    unions = [u for u in (_load_union(store, fid) for fid in p.family_spouse_ids) if u is not None]
    children_by_union: dict[str, list[PersonSummary]] = {}
    for u in unions:
        children_by_union[u.id] = [
            _person_to_summary(store, store.persons[cid])
            for cid in u.children_ids
            if cid in store.persons
        ]

    return FamilyView(
        person=person,
        father=father,
        mother=mother,
        siblings=siblings,
        unions=unions,
        children_by_union=children_by_union,
    )


def search_events(
    store: GedcomStore,
    *,
    tag: str | None = None,
    title: str | None = None,
    place: str | None = None,
    person_id: str | None = None,
    after_year: int | None = None,
    before_year: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> EventSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    ftag = tag.upper() if tag else None
    ftitle = fold(title)
    fplace = fold(place)

    person_event_ids: set[str] | None = None
    if person_id is not None:
        p = store.persons.get(person_id)
        person_event_ids = set(p.event_ids) if p else set()

    matches: list[Event] = []
    for ev in store.events.values():
        if ftag and ev.tag != ftag:
            continue
        if ftitle and (not ev.title or ftitle not in fold(ev.title)):
            continue
        if fplace and (not ev.place or fplace not in fold(ev.place.name)):
            continue
        if person_event_ids is not None and ev.id not in person_event_ids:
            continue
        if after_year is not None and (ev.year is None or ev.year < after_year):
            continue
        if before_year is not None and (ev.year is None or ev.year > before_year):
            continue
        matches.append(ev)

    matches.sort(key=lambda e: (e.year if e.year is not None else 9999, e.id))
    total = len(matches)
    page = matches[offset : offset + limit]
    return EventSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        items=[_event_to_summary(e) for e in page],
    )


def get_event(store: GedcomStore, event_id: str) -> EventDetail | None:
    ev = store.events.get(event_id)
    if ev is None:
        return None
    base = _event_to_summary(ev)
    return EventDetail(
        **base.model_dump(),
        cause=ev.cause,
        age=ev.age,
        notes=ev.notes,
        source_ids=ev.source_ids,
        participants=ev.participants,
    )


def search_places(
    store: GedcomStore, query: str, *, limit: int = 20, offset: int = 0
) -> PlaceSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    fq = fold(query)
    matches = [pl for pl in store.places.values() if fq in fold(pl.name)]
    matches.sort(key=lambda p: fold(p.name))
    total = len(matches)
    page = matches[offset : offset + limit]
    return PlaceSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        items=[PlaceRef(id=p.id, name=p.name) for p in page],
    )


def search_sources(
    store: GedcomStore, query: str, *, limit: int = 20, offset: int = 0
) -> SourceSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    fq = fold(query)
    matches = [
        s
        for s in store.sources.values()
        if fq in fold(s.title) or fq in fold(s.author) or fq in fold(s.publication)
    ]
    matches.sort(key=lambda s: fold(s.title))
    total = len(matches)
    page = matches[offset : offset + limit]
    return SourceSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        items=[_source_to_summary(s) for s in page],
    )


def _source_to_summary(s) -> SourceSummary:
    return SourceSummary(
        id=s.id,
        title=s.title,
        author=s.author,
        publication=s.publication,
        repository_id=s.repository_id,
        repository_title=s.repository_title,
        abbreviation=s.abbreviation,
        text=s.text,
    )


def get_source(store: GedcomStore, source_id: str) -> SourceSummary | None:
    s = store.sources.get(source_id)
    if s is None:
        return None
    return _source_to_summary(s)
