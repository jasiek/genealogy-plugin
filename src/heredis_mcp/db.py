"""Read-only SQLite connection helpers and value coercion."""

from __future__ import annotations

import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

from heredis_mcp.constants import COORD_NONE, DATE_TRI_NONE, SEX_FROM_CODE


def open_ro(db_path: Path | str) -> sqlite3.Connection:
    """Open the Heredis file read-only with row access by name."""
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


def fold_ucd(s: str) -> str:
    """Match Heredis's *UCD column folding: NFD, drop combining marks, uppercase.

    Heredis stores `<field>` and `<field>UCD` side by side; the UCD twin is what
    you compare against for case- and accent-insensitive search.
    """
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.upper()


def date_to_datetri(d: date) -> float:
    """Convert a Python date to Heredis's DateTri (Julian-day × 1440 minutes).

    Verified against the file: bare year "2000" → 3_530_224_800.0 = JD 2451545 × 1440.
    """
    return float((d.toordinal() + 1_721_425) * 1440)


def year_bounds(start_year: int | None, end_year: int | None) -> tuple[float, float]:
    """Return (lower, upper) DateTri bounds covering the inclusive year range.

    Either bound may be None to leave that side open.
    """
    lower = date_to_datetri(date(start_year, 1, 1)) if start_year is not None else 0.0
    upper = date_to_datetri(date(end_year + 1, 1, 1)) if end_year is not None else DATE_TRI_NONE - 1
    return lower, upper


def sex_label(code: int | None) -> str | None:
    if code is None:
        return None
    return SEX_FROM_CODE.get(code, "U")


def coord_or_none(value: float | None) -> float | None:
    if value is None or value == COORD_NONE:
        return None
    return value


def datetri_or_none(value: float | None) -> float | None:
    if value is None or value == 0.0 or value == DATE_TRI_NONE:
        return None
    return value
