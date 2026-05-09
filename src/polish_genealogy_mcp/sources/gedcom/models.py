"""Pydantic models for GEDCOM tool return shapes.

Mirrors the shape of the heredis models but uses string xref ids (the
GEDCOM `@I1@` / `@F1@` / `@S1@` style) instead of integer CodeIDs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlaceRef(BaseModel):
    id: str
    name: str

    @property
    def display(self) -> str:
        return self.name


class EventSummary(BaseModel):
    id: str
    tag: str
    date: str | None = None
    year: int | None = None
    place: PlaceRef | None = None
    title: str | None = None
    owner_id: str | None = None


class PersonSummary(BaseModel):
    id: str
    surname: str
    given_names: str
    sex: str | None = None
    birth: EventSummary | None = None
    death: EventSummary | None = None


class UnionSummary(BaseModel):
    id: str
    husband_id: str | None = None
    wife_id: str | None = None
    marriage: EventSummary | None = None
    children_ids: list[str] = Field(default_factory=list)


class PersonDetail(PersonSummary):
    nickname: str | None = None
    title: str | None = None
    occupation: str | None = None
    father_id: str | None = None
    mother_id: str | None = None
    family_child_id: str | None = None
    n_unions: int = 0
    n_children: int = 0
    events: list[EventSummary] = Field(default_factory=list)
    unions: list[UnionSummary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class FamilyView(BaseModel):
    person: PersonSummary
    father: PersonSummary | None = None
    mother: PersonSummary | None = None
    siblings: list[PersonSummary] = Field(default_factory=list)
    unions: list[UnionSummary] = Field(default_factory=list)
    children_by_union: dict[str, list[PersonSummary]] = Field(default_factory=dict)


class EventDetail(EventSummary):
    cause: str | None = None
    age: str | None = None
    notes: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    participants: list[dict] = Field(default_factory=list)


class SourceSummary(BaseModel):
    id: str
    title: str | None = None
    author: str | None = None
    publication: str | None = None
    repository_id: str | None = None
    repository_title: str | None = None
    abbreviation: str | None = None
    text: str | None = None


class PersonSearchResult(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PersonSummary]


class EventSearchResult(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EventSummary]


class PlaceSearchResult(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PlaceRef]


class SourceSearchResult(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SourceSummary]
