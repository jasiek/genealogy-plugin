"""Pydantic models for the Genealogy Indexer source."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenealogyIndexerMatch(BaseModel):
    """One source page that matched the query.

    Genealogy Indexer groups its hits by *source page*: a single match here
    is one scanned page of one source, with one or more ``snippets`` of
    surrounding OCR text (matched terms wrapped in ``**bold**``) and/or, when
    the page is a tabular directory, structured ``entries`` (one dict per row,
    keyed by the table's column headers — typically Last Name / First Name /
    Occupation / Address).

    ``scan_url`` links to the digitised page image (resolved to an absolute
    URL; it points either at the hosting library or at a Genealogy Indexer
    ``/frame/…`` viewer). The ``source_*`` fields and ``date_added`` come from
    the entry's "About this source" panel.
    """

    title: str | None = None
    scan_url: str | None = None
    image_label: str | None = None
    image_number: int | None = None
    source_id: str | None = None
    source_title: str | None = None
    images_from: str | None = None
    images_from_url: str | None = None
    date_added: str | None = None
    snippets: list[str] = Field(default_factory=list)
    entries: list[dict[str, str]] = Field(default_factory=list)


class GenealogyIndexerSearchResult(BaseModel):
    query: str | None = None
    # The upstream "Matches Found" count. This counts individual matches, so
    # it can exceed ``returned``: hits are grouped by source page (one item
    # per page), and for very common terms the site caps how many it renders.
    total: int = 0
    # Number of source-page items returned (after any ``max_results`` cap).
    returned: int = 0
    # True when the listing is incomplete: either the site capped a very
    # common query, or ``max_results`` truncated the items.
    truncated: bool = False
    items: list[GenealogyIndexerMatch] = Field(default_factory=list)
