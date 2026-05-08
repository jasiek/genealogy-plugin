"""Pydantic models returned by Geneteka tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecordType = Literal["birth", "marriage", "death"]


class GenetekaRegion(BaseModel):
    code: str
    name: str


class GenetekaPerson(BaseModel):
    """One person within a Geneteka record.

    For births and deaths the indexed person is the child / decedent and
    `father_given`, `mother_given`, `mother_maiden` carry parents. For
    marriages the upstream column is "Rodzice" — a free-form combined string
    we surface as `parents` rather than splitting heuristically.
    """

    given_name: str | None = None
    surname: str | None = None
    father_given: str | None = None
    mother_given: str | None = None
    mother_maiden: str | None = None
    parents: str | None = None


class GenetekaRecord(BaseModel):
    record_type: RecordType
    gid: int | None = None
    year: int | None = None
    act_no: str | None = None
    parish: str | None = None
    place: str | None = None
    region_code: str
    person: GenetekaPerson
    spouse: GenetekaPerson | None = None
    comments: str | None = None
    archive: str | None = None
    indexer: str | None = None
    fix_url: str | None = None


class GenetekaSearchResult(BaseModel):
    record_type: RecordType
    region_code: str
    region_name: str | None = None
    total: int
    limit: int
    offset: int
    items: list[GenetekaRecord] = Field(default_factory=list)
