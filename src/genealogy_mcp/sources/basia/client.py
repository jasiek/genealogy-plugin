"""Synchronous httpx client for the BaSIA archival index."""

from __future__ import annotations

import datetime
import os
import threading
import time
from dataclasses import dataclass

import httpx

from genealogy_mcp.sources._http_retry import RetryTransport
from genealogy_mcp.sources.basia.constants import (
    DEFAULT_BASE_URL,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_SIMILARITY,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    RECORD_TYPE_TO_FORM,
    RELATION_TO_FORM,
    SEARCH_PATH,
    SEX_TO_FORM,
    UNIT_TYPE_TO_FORM,
    YEAR_MIN,
)
from genealogy_mcp.sources.basia.models import BasiaSearchResult
from genealogy_mcp.sources.basia.parser import parse_search_response


@dataclass
class BasiaConfig:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "BasiaConfig":
        interval_env = os.environ.get("BASIA_MIN_INTERVAL")
        ua_env = os.environ.get("BASIA_USER_AGENT")
        timeout_env = os.environ.get("BASIA_TIMEOUT")
        return cls(
            min_interval_seconds=(
                float(interval_env) if interval_env else DEFAULT_MIN_INTERVAL_SECONDS
            ),
            user_agent=ua_env or DEFAULT_USER_AGENT,
            timeout_seconds=(float(timeout_env) if timeout_env else DEFAULT_TIMEOUT_SECONDS),
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


class BasiaClient:
    """Synchronous client for the BaSIA advanced-search endpoint.

    The upstream form POSTs ``application/x-www-form-urlencoded`` to ``/``
    and returns the rendered results page. The search runs a fuzzy name
    match over the whole 6.6M-entry base server-side, so it is slow; the
    client uses a long default timeout and a browser-style User-Agent.
    """

    def __init__(
        self,
        config: BasiaConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or BasiaConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            transport=RetryTransport(transport),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BasiaClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search(
        self,
        *,
        surname: str | None = None,
        given_name: str | None = None,
        sex: str = "any",
        relation: str = "any",
        similarity: int = DEFAULT_SIMILARITY,
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
        distance_km: int = 10,
        record_type: str = "any",
        unit_type: str = "any",
        max_results: int | None = None,
    ) -> BasiaSearchResult:
        if not surname and not given_name and not place:
            raise ValueError("BaSIA search needs at least a surname, given_name, or place.")

        try:
            sex_v = SEX_TO_FORM[sex]
        except KeyError as exc:
            raise ValueError(f"Unknown sex {sex!r}. Known: {', '.join(SEX_TO_FORM)}") from exc
        try:
            relation_v = RELATION_TO_FORM[relation]
        except KeyError as exc:
            raise ValueError(
                f"Unknown relation {relation!r}. Known: {', '.join(RELATION_TO_FORM)}"
            ) from exc
        try:
            record_v = RECORD_TYPE_TO_FORM[record_type]
        except KeyError as exc:
            raise ValueError(
                f"Unknown record_type {record_type!r}. " f"Known: {', '.join(RECORD_TYPE_TO_FORM)}"
            ) from exc
        try:
            unit_v = UNIT_TYPE_TO_FORM[unit_type]
        except KeyError as exc:
            raise ValueError(
                f"Unknown unit_type {unit_type!r}. " f"Known: {', '.join(UNIT_TYPE_TO_FORM)}"
            ) from exc

        sim = max(0, min(100, int(similarity)))
        od = YEAR_MIN if from_year is None else int(from_year)
        do = datetime.date.today().year if to_year is None else int(to_year)

        data: dict[str, str] = {
            "fname0": given_name or "",
            "lname0": surname or "",
            "sex0": sex_v,
            "type0": relation_v,
            "sim0": str(sim),
            "p_count": "1",
            "od": str(od),
            "do": str(do),
            # Toggle hidden inputs gate whether the place / type / date
            # filters are honoured; only flip them on when used.
            "showplaces": "block" if place else "none",
            "showtype": "block" if (record_v != "any" or unit_v != "any") else "none",
            "showdate": "none",
            "type_unit": unit_v,
            "type_record": record_v,
            "search_ext": "szukaj",
            "search_ext_button": "Szukaj",
        }
        if place:
            data["placename"] = place
            data["distance"] = str(int(distance_km))

        self._limiter.wait()
        resp = self._client.post(
            SEARCH_PATH,
            data=data,
            headers={"Referer": self.config.base_url + "/"},
        )
        resp.raise_for_status()
        text = resp.content.decode("utf-8", errors="replace")
        return parse_search_response(
            text,
            surname_query=surname,
            given_name_query=given_name,
            base_url=self.config.base_url,
            max_results=max_results,
        )
