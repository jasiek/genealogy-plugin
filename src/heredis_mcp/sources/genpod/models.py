"""Pydantic models returned by GenPod tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GenpodRecordType = Literal["birth", "marriage", "death"]


class GenpodSearchResult(BaseModel):
    """Search results returned from GenPod's GraphQL API."""

    filters: dict[str, Any] = Field(default_factory=dict)
    total: dict[str, int | None] = Field(default_factory=dict)
    items: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    warnings: dict[str, str | None] = Field(default_factory=dict)


class GenpodParishIndexingStatus(BaseModel):
    totalCount: int = 0
    years: list[int] = Field(default_factory=list)
    sourceFiles: list[dict[str, Any]] = Field(default_factory=list)


class GenpodParishSummary(BaseModel):
    name: str
    katalogId: int | None = None
    mostRecentRecordDate: str | None = None
    urodzenia: GenpodParishIndexingStatus
    malzenstwa: GenpodParishIndexingStatus
    zgony: GenpodParishIndexingStatus
    totalDocuments: int = 0


class GenpodParishCoverageResult(BaseModel):
    parishes: list[GenpodParishSummary] = Field(default_factory=list)
    updateHistogram: list[dict[str, Any]] = Field(default_factory=list)


class GenpodParishYearImport(BaseModel):
    year: int
    recordType: str
    importDate: str


class GenpodParishYearImportsResult(BaseModel):
    parafiaName: str
    imports: list[GenpodParishYearImport] = Field(default_factory=list)
