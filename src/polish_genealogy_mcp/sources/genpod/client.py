"""Authenticated HTTP/GraphQL client for GenPod."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from polish_genealogy_mcp.sources.genpod.constants import (
    BASE_URL,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    GRAPHQL_PATH,
    LOGIN_PATH,
)
from polish_genealogy_mcp.sources.genpod.models import GenpodRecordType

SEARCH_VITAL_RECORDS_QUERY = """
query SearchVitalRecords(
  $commonFilters: CommonFilters
  $sliceUrodzenia: Slice!
  $sliceMalzenstwa: Slice!
  $sliceZgony: Slice!
) {
  urodzenia(slice: $sliceUrodzenia, commonFilters: $commonFilters) {
    totalResultCount
    pageSize
    didNotProvideLastNameFragment
    results {
      mysql_id
      mysql_date_time
      rok
      akt
      imie_pierwsze
      nazwisko_wsp
      ojciec_imie
      matka_imie
      matka_nazwisko
      parafia_nazwa
      parafia_katalog_id
      miejscowosc
      uwagi
      nazwisko_oryg
    }
  }
  malzenstwa(slice: $sliceMalzenstwa, commonFilters: $commonFilters) {
    totalResultCount
    pageSize
    didNotProvideLastNameFragment
    results {
      mysql_id
      mysql_date_time
      rok
      akt
      maz_imie_pierwsze
      maz_imie_drugie
      maz_nazwisko_wsp
      maz_nazwisko_oryg
      maz_ojciec_imie
      maz_matka_imie
      maz_matka_nazwisko
      zona_imie_pierwsze
      zona_imie_drugie
      zona_nazwisko_wsp
      zona_nazwisko_oryg
      zona_ojciec_imie
      zona_matka_imie
      zona_matka_nazwisko
      parafia_nazwa
      parafia_katalog_id
      miejscowosc
      uwagi
    }
  }
  zgony(slice: $sliceZgony, commonFilters: $commonFilters) {
    totalResultCount
    pageSize
    didNotProvideLastNameFragment
    results {
      mysql_id
      mysql_date_time
      rok
      akt
      imie_pierwsze
      nazwisko_wsp
      ojciec_imie
      matka_imie
      matka_nazwisko
      parafia_nazwa
      parafia_katalog_id
      miejscowosc
      uwagi
      nazwisko_oryg
    }
  }
}
"""

LIST_PARISHES_QUERY = """
query GetZindeksowaneParafie {
  parafieIndexingSummary {
    name
    katalogId
    mostRecentRecordDate
    urodzenia {
      ...ParafiaDbIndexingStatus
    }
    malzenstwa {
      ...ParafiaDbIndexingStatus
    }
    zgony {
      ...ParafiaDbIndexingStatus
    }
    totalDocuments
  }
  parafieUpdateHistogram {
    buckets {
      date
      parafieCount
      parafieNames
    }
  }
}

fragment ParafiaDbIndexingStatus on ParafiaDbIndexingStatus {
  totalCount
  years
  sourceFiles {
    sourceDocName
    recordCount
    recordCountUpperBound
  }
}
"""

PARISH_YEAR_IMPORTS_QUERY = """
query GetParafiaYearImports($parafiaName: String!) {
  parafiaYearImports(parafiaName: $parafiaName) {
    parafiaName
    imports {
      year
      recordType
      importDate
    }
  }
}
"""

REACT_CONTEXT_RE = re.compile(r"window\.reactContext\s*=\s*(?P<context>\{.*?\});", re.DOTALL)


@dataclass
class GenpodConfig:
    base_url: str = BASE_URL
    username: str | None = None
    password: str | None = None
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GenpodConfig":
        interval_env = os.environ.get("GENPOD_MIN_INTERVAL")
        base_url = os.environ.get("GENPOD_BASE_URL")
        user_agent = os.environ.get("GENPOD_USER_AGENT")
        return cls(
            base_url=base_url or BASE_URL,
            username=os.environ.get("GENPOD_USERNAME"),
            password=os.environ.get("GENPOD_PASSWORD"),
            min_interval_seconds=(
                float(interval_env) if interval_env else DEFAULT_MIN_INTERVAL_SECONDS
            ),
            user_agent=user_agent or DEFAULT_USER_AGENT,
        )


class GenpodAuthenticationError(RuntimeError):
    """Raised when GenPod credentials are missing or rejected."""


class _RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_for = self._min_interval - (now - self._last)
            if wait_for > 0:
                time.sleep(wait_for)
            self._last = time.monotonic()


class GenpodClient:
    """Synchronous authenticated client for GenPod's same-origin GraphQL API."""

    def __init__(
        self,
        config: GenpodConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or GenpodConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/json, text/plain, */*",
            },
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._authenticated = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GenpodClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search_vital_records(
        self,
        *,
        last_name: str | None = None,
        first_name: str | None = None,
        last_name_exact: bool = False,
        second_person_last_name: str | None = None,
        second_person_last_name_exact: bool = False,
        year_from: int | None = None,
        year_to: int | None = None,
        parish_id: int | None = None,
        wyznanie: str | None = None,
        record_types: list[GenpodRecordType] | None = None,
        limit: int = 25,
        page: int = 1,
    ) -> dict[str, Any]:
        page_size = max(1, min(int(limit), 50))
        page_no = max(1, int(page))
        requested = set(record_types or ["birth", "marriage", "death"])
        disabled = {"page": 1, "pageSize": 1, "sortColumn": "rok", "sortOrder": "ASCENDING"}
        variables = {
            "commonFilters": _without_none(
                {
                    "lastNameFragment": last_name,
                    "lastNameExact": last_name_exact,
                    "firstNameFragment": first_name,
                    "yearFromInclusive": year_from,
                    "yearToInclusive": year_to,
                    "parafiaId": parish_id,
                    "wyznanie": wyznanie,
                    "secondPersonLastNameFragment": second_person_last_name,
                    "secondPersonLastNameExact": second_person_last_name_exact,
                }
            ),
            "sliceUrodzenia": (
                _slice(page_no, page_size, "rok") if "birth" in requested else disabled
            ),
            "sliceMalzenstwa": (
                _slice(page_no, page_size, "rok") if "marriage" in requested else disabled
            ),
            "sliceZgony": _slice(page_no, page_size, "rok") if "death" in requested else disabled,
        }
        data = self.graphql(
            SEARCH_VITAL_RECORDS_QUERY,
            operation_name="SearchVitalRecords",
            variables=variables,
        )
        for record_type, gql_name in {
            "birth": "urodzenia",
            "marriage": "malzenstwa",
            "death": "zgony",
        }.items():
            if record_type not in requested and isinstance(data.get(gql_name), dict):
                data[gql_name] = {
                    **data[gql_name],
                    "totalResultCount": None,
                    "results": [],
                    "didNotProvideLastNameFragment": False,
                }
        return data

    def list_parishes(self) -> dict[str, Any]:
        return self.graphql(LIST_PARISHES_QUERY, operation_name="GetZindeksowaneParafie")

    def get_parish_year_imports(self, parish_name: str) -> dict[str, Any]:
        return self.graphql(
            PARISH_YEAR_IMPORTS_QUERY,
            operation_name="GetParafiaYearImports",
            variables={"parafiaName": parish_name},
        )

    def graphql(
        self,
        query: str,
        *,
        operation_name: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_authenticated()
        self._limiter.wait()
        resp = self._client.post(
            GRAPHQL_PATH,
            json={
                "operationName": operation_name,
                "variables": variables or {},
                "query": query,
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        payload = resp.json()
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"GenPod GraphQL error: {errors}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("GenPod GraphQL response did not contain a data object.")
        return data

    def _ensure_authenticated(self) -> None:
        if self._authenticated:
            return
        if not self.config.username or not self.config.password:
            raise GenpodAuthenticationError(
                "GenPod credentials are required. Set GENPOD_USERNAME and GENPOD_PASSWORD."
            )

        self._limiter.wait()
        self._client.get(LOGIN_PATH).raise_for_status()
        self._limiter.wait()
        login = self._client.post(
            LOGIN_PATH,
            data={"username": self.config.username, "password": self.config.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login.raise_for_status()
        user = _react_context_user(login.text)
        if user is None:
            self._limiter.wait()
            home = self._client.get("/")
            home.raise_for_status()
            user = _react_context_user(home.text)
        if user is None:
            raise GenpodAuthenticationError(
                "GenPod login did not produce an authenticated session."
            )
        self._authenticated = True


def _slice(page: int, page_size: int, sort_column: str) -> dict[str, Any]:
    return {
        "page": page,
        "pageSize": page_size,
        "sortColumn": sort_column,
        "sortOrder": "ASCENDING",
    }


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _react_context_user(html: str) -> Any | None:
    match = REACT_CONTEXT_RE.search(html)
    if not match:
        return None
    try:
        context = json.loads(match.group("context"))
    except json.JSONDecodeError:
        return None
    return context.get("user")
