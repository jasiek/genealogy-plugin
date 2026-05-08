from datetime import date

import pytest

from heredis_mcp.db import (
    coord_or_none,
    date_to_datetri,
    datetri_or_none,
    fold_ucd,
    sex_label,
    year_bounds,
)


def test_fold_ucd_uppercases_and_strips_diacritics():
    assert fold_ucd("Évariste") == "EVARISTE"
    assert fold_ucd("Łódź") == "ŁODZ"  # Ł has no combining diacritic; only ó/ź fold
    assert fold_ucd("") == ""


def test_date_to_datetri_matches_known_anchor():
    # Verified against the Heredis file: bare-year "2000" -> 3_530_224_800.
    assert date_to_datetri(date(2000, 1, 1)) == 3_530_224_800.0


def test_year_bounds_inclusive():
    lo, hi = year_bounds(1850, 1850)
    # 1850-01-01 .. 1851-01-01 covers the whole year.
    assert lo == date_to_datetri(date(1850, 1, 1))
    assert hi == date_to_datetri(date(1851, 1, 1))


def test_year_bounds_open_ended():
    lo, hi = year_bounds(None, 1900)
    assert lo == 0.0
    assert hi == date_to_datetri(date(1901, 1, 1))


def test_sex_label():
    assert sex_label(109) == "M"
    assert sex_label(102) == "F"
    assert sex_label(63) == "U"
    assert sex_label(None) is None
    assert sex_label(0) == "U"  # unknown code defaults to U


def test_coord_or_none_handles_sentinel():
    assert coord_or_none(2_000_000.0) is None
    assert coord_or_none(48.85) == 48.85
    assert coord_or_none(None) is None


def test_datetri_or_none_handles_sentinels():
    assert datetri_or_none(0.0) is None
    assert datetri_or_none(100_000_000_000.0) is None
    assert datetri_or_none(3_530_224_800.0) == 3_530_224_800.0


def test_open_ro_rejects_writes(conn):
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE __probe (x INTEGER)")
