"""Pydantic models for the BaSIA source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecordType = Literal["birth", "marriage", "death", "banns", "other"]


class BasiaRecord(BaseModel):
    """One indexed entry from a BaSIA search-results page.

    BaSIA indexes the *principal* person of each act plus, often, their
    parents, spouse, and other people named in the document. ``given_name``
    / ``surname`` are a best-effort split of the indexed full name on the
    first space — Polish maiden-name suffixes (e.g. "ze Zwolinskich") and
    single-name child entries make this imperfect, so ``name`` keeps the
    verbatim string.

    ``scan_url`` links to a digitised image (typically on
    ``szukajwarchiwach.gov.pl`` / ``szukajwarchiwach.pl`` or
    ``familysearch.org``) when the indexer recorded one. ``permalink`` is a
    stable BaSIA URL for the entry. ``similarity`` is the fuzzy-match score
    (percent) the upstream assigned to this hit.
    """

    record_id: str | None = None
    record_type: RecordType
    record_type_label: str | None = None
    place: str | None = None
    unit_type: str | None = None
    year: int | None = None
    book_title: str | None = None
    name: str | None = None
    given_name: str | None = None
    surname: str | None = None
    age: str | None = None
    father: str | None = None
    mother: str | None = None
    parents_raw: str | None = None
    spouse: str | None = None
    similarity: int | None = None
    other_persons: list[str] = Field(default_factory=list)
    indexer_comment: str | None = None
    archive: str | None = None
    signature: str | None = None
    scan_url: str | None = None
    scan_label: str | None = None
    indexer: str | None = None
    date_added: str | None = None
    permalink: str | None = None


class BasiaSearchResult(BaseModel):
    surname_query: str | None = None
    given_name_query: str | None = None
    # Number of matches by record type (over the returned items).
    counts: dict[str, int] = Field(default_factory=dict)
    # Total matches the page contained, before any ``max_results`` cap.
    total: int = 0
    # True when ``max_results`` truncated the returned items.
    truncated: bool = False
    # Server-reported search time, parsed from "Czas wyszukiwania: N s".
    search_time_seconds: float | None = None
    items: list[BasiaRecord] = Field(default_factory=list)
