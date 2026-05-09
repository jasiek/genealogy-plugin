"""Synchronous httpx client for the Lubgens regional index."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Iterable

import httpx

from polish_genealogy_mcp.sources.lubgens.constants import (
    DEFAULT_BASE_URL,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    RECORD_TYPE_TO_FIELD,
    SEARCH_PATH,
    WILDMODE_TO_INT,
)
from polish_genealogy_mcp.sources.lubgens.models import LubgensSearchResult, RecordType
from polish_genealogy_mcp.sources.lubgens.parser import parse_search_response


@dataclass
class LubgensConfig:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "LubgensConfig":
        interval_env = os.environ.get("LUBGENS_MIN_INTERVAL")
        ua_env = os.environ.get("LUBGENS_USER_AGENT")
        return cls(
            min_interval_seconds=(
                float(interval_env) if interval_env else DEFAULT_MIN_INTERVAL_SECONDS
            ),
            user_agent=ua_env or DEFAULT_USER_AGENT,
        )


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


class LubgensClient:
    """Synchronous client for the Lubgens search endpoint.

    The upstream form POSTs ``application/x-www-form-urlencoded`` and
    returns the rendered results page. The site rejects bot user-agents,
    so we set a browser-style UA by default.
    """

    def __init__(
        self,
        config: LubgensConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or LubgensConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LubgensClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search(
        self,
        *,
        surname: str | None = None,
        given_name: str | None = None,
        record_types: Iterable[RecordType] = ("birth", "marriage", "death"),
        from_year: int | None = None,
        to_year: int | None = None,
        wildmode: str = "prefix",
        include_remarks: bool = False,
    ) -> LubgensSearchResult:
        try:
            mode = WILDMODE_TO_INT[wildmode]
        except KeyError as exc:
            known = ", ".join(sorted(WILDMODE_TO_INT))
            raise ValueError(f"Unknown wildmode {wildmode!r}. Known: {known}") from exc

        types = list(record_types) or ["birth", "marriage", "death"]
        for t in types:
            if t not in RECORD_TYPE_TO_FIELD:
                raise ValueError(f"Unknown record_type {t!r}")

        data: dict[str, str] = {}
        for t in types:
            data[RECORD_TYPE_TO_FIELD[t]] = "1"
        if include_remarks:
            data["uwagi"] = "1"
        data.update(
            {
                "parafia": "",
                "nazwisko": surname or "",
                "wildmode": str(mode),
                "imie": given_name or "",
                "rok_od": "" if from_year is None else str(from_year),
                "rok_do": "" if to_year is None else str(to_year),
                "sort1": "1",
                "sort2": "3",
                "sort3": "1",
            }
        )

        self._limiter.wait()
        resp = self._client.post(
            SEARCH_PATH,
            data=data,
            headers={"Referer": f"{self.config.base_url}/news.php"},
        )
        resp.raise_for_status()
        # Upstream occasionally splits a multi-byte UTF-8 character with
        # an inline <span> highlight wrapper, leaving stray invalid
        # bytes; decode tolerantly so a single corrupted note doesn't
        # blow up the whole response.
        text = resp.content.decode("utf-8", errors="replace")
        return parse_search_response(
            text,
            surname_query=surname,
            given_name_query=given_name,
        )
