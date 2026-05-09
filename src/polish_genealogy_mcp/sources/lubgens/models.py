"""Pydantic models for the Lubgens source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecordType = Literal["birth", "marriage", "death"]


class LubgensRecord(BaseModel):
    """One indexed vital record row from the Lubgens search results.

    Marriage rows carry both bride and groom; for births and deaths the
    ``spouse_*`` fields are ``None``. ``father_name`` / ``mother_name``
    are best-effort extractions from the ``UWAGI`` (notes) cell — the
    upstream encodes parents inline as ``O: <name>, M: <name>`` (or
    ``On- O: ..., M: ..., Ona- O: ..., M: ...`` for marriages, in which
    case only the groom's parents land in these fields and the rest stay
    in ``notes``).
    """

    record_type: RecordType
    surname: str | None = None
    given_name: str | None = None
    spouse_surname: str | None = None
    spouse_given_name: str | None = None
    parish: str | None = None
    act_number: str | None = None
    year: int | None = None
    father_name: str | None = None
    mother_name: str | None = None
    scan_url: str | None = None
    notes: str | None = None


class LubgensSearchResult(BaseModel):
    surname_query: str | None = None
    given_name_query: str | None = None
    truncated: dict[str, bool] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[LubgensRecord] = Field(default_factory=list)
