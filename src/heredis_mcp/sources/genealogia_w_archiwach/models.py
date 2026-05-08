"""Pydantic models returned by Genealogia w Archiwach tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ActType = Literal["birth", "death", "marriage"]
PersonRole = Literal["deceased", "child", "mother", "father", "bride", "groom", "all"]
SearchScope = Literal["all", "units", "indexes", "people", "pradziad"]


class GenealogiaWArchiwachRecord(BaseModel):
    """One candidate result from Genealogia w Archiwach."""

    title: str | None = None
    description: str | None = None
    year: int | None = None
    place: str | None = None
    act_type: ActType | None = None
    role: PersonRole | None = None
    source_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    identifiers: dict[str, str] = Field(default_factory=dict)
    raw_text: str | None = None


class GenealogiaWArchiwachSearchResult(BaseModel):
    query: str | None = None
    given_name: str | None = None
    surname: str | None = None
    scope: SearchScope
    total: int | None = None
    items: list[GenealogiaWArchiwachRecord] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    warning: str | None = None
