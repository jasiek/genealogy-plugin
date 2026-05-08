"""Pydantic models for tool return shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlaceRef(BaseModel):
    code_id: int
    city: str | None = None
    department: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def display(self) -> str:
        parts = [p for p in (self.city, self.department, self.region, self.country) if p]
        return ", ".join(parts)


class EventSummary(BaseModel):
    code_id: int
    event_type: int
    event_type_label: str
    date_ged: str | None = None
    date_tri: float | None = None
    place: PlaceRef | None = None
    title: str | None = None


class PersonSummary(BaseModel):
    code_id: int
    surname: str
    given_names: str
    sex: str | None = None
    birth: EventSummary | None = None
    death: EventSummary | None = None


class UnionSummary(BaseModel):
    code_id: int
    type: str
    husband_id: int | None = None
    wife_id: int | None = None
    marriage: EventSummary | None = None
    children_ids: list[int] = Field(default_factory=list)


class PersonDetail(PersonSummary):
    prefix: str | None = None
    suffix: str | None = None
    nickname: str | None = None
    title: str | None = None
    occupation: str | None = None
    confidential: bool = False
    father_id: int | None = None
    mother_id: int | None = None
    union_parents_id: int | None = None
    n_unions: int = 0
    n_children: int = 0
    n_sources: int = 0
    n_medias: int = 0
    sosa_number: str | None = None
    sosa_generation: int | None = None
    events: list[EventSummary] = Field(default_factory=list)
    unions: list[UnionSummary] = Field(default_factory=list)


class FamilyView(BaseModel):
    person: PersonSummary
    father: PersonSummary | None = None
    mother: PersonSummary | None = None
    siblings: list[PersonSummary] = Field(default_factory=list)
    unions: list[UnionSummary] = Field(default_factory=list)
    children_by_union: dict[int, list[PersonSummary]] = Field(default_factory=dict)


class EventDetail(EventSummary):
    cause: str | None = None
    age_on_act: str | None = None
    private: bool = False
    shared: bool = False
    owner_person_id: int | None = None
    owner_union_id: int | None = None
    participants: list[dict] = Field(default_factory=list)
    n_sources: int = 0
    n_medias: int = 0


class SourceSummary(BaseModel):
    code_id: int
    title: str | None = None
    document: str | None = None
    author: str | None = None
    repository_id: int | None = None
    repository_title: str | None = None
    url: str | None = None
    date_ged: str | None = None


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
