"""Thin httpx wrapper over Geneteka's `api/getAct.php` endpoint."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import httpx

from heredis_mcp.sources.geneteka.constants import (
    API_PATH,
    BASE_URL,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    RECORD_TYPE_TO_BDM,
)
from heredis_mcp.sources.geneteka.models import RecordType


@dataclass
class GenetekaConfig:
    base_url: str = BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GenetekaConfig":
        interval_env = os.environ.get("GENETEKA_MIN_INTERVAL")
        ua_env = os.environ.get("GENETEKA_USER_AGENT")
        return cls(
            min_interval_seconds=(
                float(interval_env) if interval_env else DEFAULT_MIN_INTERVAL_SECONDS
            ),
            user_agent=ua_env or DEFAULT_USER_AGENT,
        )


class _RateLimiter:
    """Process-wide minimum interval between calls."""

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


class GenetekaClient:
    """Synchronous client. One instance per server is enough (httpx pool inside)."""

    def __init__(self, config: GenetekaConfig | None = None) -> None:
        self.config = config or GenetekaConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "User-Agent": self.config.user_agent,
                # Geneteka's API rejects requests without a same-site Referer.
                "Referer": f"{self.config.base_url}/",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GenetekaClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search(
        self,
        *,
        record_type: RecordType,
        region_code: str,
        surname: str | None = None,
        surname2: str | None = None,
        given_name: str | None = None,
        given_name2: str | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
        parish_id: str | None = None,
        exact: bool = False,
        start: int = 0,
        length: int = 25,
    ) -> dict:
        """Issue a search and return the parsed JSON payload as-is.

        The DataTables-compatible response has the shape
        `{draw, recordsTotal, recordsFiltered, data: [[...], ...]}`.
        """
        bdm = RECORD_TYPE_TO_BDM[record_type]
        params: dict[str, str | int] = {
            "op": "gt",
            "lang": "pol",
            "bdm": bdm,
            "w": region_code,
            "search_lastname": surname or "",
            "search_lastname2": surname2 or "",
            "search_name": given_name or "",
            "search_name2": given_name2 or "",
            "from_date": str(from_year) if from_year is not None else "",
            "to_date": str(to_year) if to_year is not None else "",
            "rid": parish_id or "",
            "search_place": place or "",
            "draw": 1,
            "start": max(0, int(start)),
            "length": max(1, min(int(length), 50)),
        }
        if exact:
            params["exac"] = 1

        self._limiter.wait()
        resp = self._client.get(API_PATH, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_regions_html(self) -> str:
        """Fetch the surname-occurrence form page (`?op=se`).

        The page lists every region as `<a ...w=CODE...>Name</a>`; downstream
        code parses that into the canonical region table. Rate-limited via
        the same limiter as `search`.
        """
        self._limiter.wait()
        resp = self._client.get(
            "/index.php",
            params={"op": "se", "lang": "pol"},
        )
        resp.raise_for_status()
        return resp.text
