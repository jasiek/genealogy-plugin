from __future__ import annotations

from pathlib import Path

import pytest

from heredis_mcp.db import open_ro

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DB = REPO_ROOT / "Szumiec.heredis"


@pytest.fixture(scope="session")
def db_path() -> Path:
    if not FIXTURE_DB.exists():
        pytest.skip(f"Fixture database not found at {FIXTURE_DB}")
    return FIXTURE_DB


@pytest.fixture
def conn(db_path: Path):
    c = open_ro(db_path)
    try:
        yield c
    finally:
        c.close()
