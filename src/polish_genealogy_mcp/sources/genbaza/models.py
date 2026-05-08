"""Pydantic models returned by genbaza tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecordType = Literal["birth", "marriage", "death"]


class GenbazaSite(BaseModel):
    code: str
    base_url: str


class GenbazaRecord(BaseModel):
    """One indexed vital record returned by a genbaza search.

    `record_type` is set on variant-A sites (which split results into
    separate births / marriages / deaths tables) and ``None`` on
    variant-B sites which return a combined table without a per-row
    record-type indicator.
    """

    site: str
    record_type: RecordType | None = None
    surname: str | None = None
    given_name: str | None = None
    father_name: str | None = None
    mother_name: str | None = None
    mother_surname: str | None = None
    parish: str | None = None
    year: int | None = None
    act_or_page: str | None = None
    notes: list[str] = Field(default_factory=list)
    archive_ref: str | None = None
    scan_url: str | None = None
    indexer: str | None = None


class GenbazaSearchResult(BaseModel):
    site: str
    page: int
    record_type: RecordType | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    total_pages: int | None = None
    items: list[GenbazaRecord] = Field(default_factory=list)


class GenbazaResource(BaseModel):
    """A parish/locality entry from the ``zasób`` (resources) catalogue."""

    site: str
    parish: str
    births: str | None = None
    marriages: str | None = None
    deaths: str | None = None


class GenbazaResourceList(BaseModel):
    site: str
    summary: str | None = None
    items: list[GenbazaResource] = Field(default_factory=list)
