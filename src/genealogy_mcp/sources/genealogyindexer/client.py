"""Synchronous httpx client for the Genealogy Indexer search endpoint."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import httpx

from genealogy_mcp.sources._http_retry import RetryTransport
from genealogy_mcp.sources.genealogyindexer.constants import (
    COLLECTION_TO_FORM,
    DATE_TO_FORM,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    MATCH_TO_FORM,
    PLACE_TO_SCOPE,
    SCOPE_CODE_RE,
    SEARCH_PATH,
    SORT_TO_FORM,
    TRANSLITERATION_TO_FORM,
)
from genealogy_mcp.sources.genealogyindexer.models import GenealogyIndexerSearchResult
from genealogy_mcp.sources.genealogyindexer.parser import parse_search_response


@dataclass
class GenealogyIndexerConfig:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "GenealogyIndexerConfig":
        interval_env = os.environ.get("GENEALOGYINDEXER_MIN_INTERVAL")
        ua_env = os.environ.get("GENEALOGYINDEXER_USER_AGENT")
        timeout_env = os.environ.get("GENEALOGYINDEXER_TIMEOUT")
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


def _resolve_scope(place: str | None) -> str:
    """Map a friendly place name or a raw scope code to a form scope value."""
    if place is None:
        return "any"
    text = place.strip()
    if not text or text.lower() == "any":
        return "any"
    code = PLACE_TO_SCOPE.get(text.lower())
    if code is not None:
        return code
    if SCOPE_CODE_RE.match(text):
        return text
    raise ValueError(
        f"Unknown place {place!r}. Pass one of: {', '.join(sorted(PLACE_TO_SCOPE))}; "
        "or a raw scope code from the site's Place dropdown."
    )


class GenealogyIndexerClient:
    """Synchronous client for the Genealogy Indexer search form.

    The single form POSTs ``application/x-www-form-urlencoded`` to ``/`` and
    returns the rendered results page. The search is full text over OCR'd
    pages and is fast; the only slow part is transferring a multi-megabyte
    page for a very common term, which the long default timeout covers.
    """

    def __init__(
        self,
        config: GenealogyIndexerConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or GenealogyIndexerConfig.from_env()
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

    def __enter__(self) -> "GenealogyIndexerClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search(
        self,
        *,
        term: str,
        place: str | None = "any",
        collection: str = "any",
        date: str = "any",
        match: str = "regular",
        sort: str = "regular",
        transliteration: str = "none",
        max_results: int | None = DEFAULT_MAX_RESULTS,
    ) -> GenealogyIndexerSearchResult:
        if not term or not term.strip():
            raise ValueError("Genealogy Indexer search needs a non-empty term.")

        scope = _resolve_scope(place)
        try:
            match_v = MATCH_TO_FORM[match]
        except KeyError as exc:
            raise ValueError(f"Unknown match {match!r}. Known: {', '.join(MATCH_TO_FORM)}") from exc
        try:
            sort_v = SORT_TO_FORM[sort]
        except KeyError as exc:
            raise ValueError(f"Unknown sort {sort!r}. Known: {', '.join(SORT_TO_FORM)}") from exc
        try:
            collection_v = COLLECTION_TO_FORM[collection]
        except KeyError as exc:
            raise ValueError(
                f"Unknown collection {collection!r}. Known: {', '.join(COLLECTION_TO_FORM)}"
            ) from exc
        try:
            date_v = DATE_TO_FORM[date]
        except KeyError as exc:
            raise ValueError(f"Unknown date {date!r}. Known: {', '.join(DATE_TO_FORM)}") from exc
        try:
            translit_v = TRANSLITERATION_TO_FORM[transliteration]
        except KeyError as exc:
            raise ValueError(
                f"Unknown transliteration {transliteration!r}. "
                f"Known: {', '.join(TRANSLITERATION_TO_FORM)}"
            ) from exc

        data: dict[str, str] = {
            "term": term,
            "search": "1",
            "scope": scope,
            "match": match_v,
            "sort": sort_v,
            "collection": collection_v,
            "date": date_v,
            "transliteration": translit_v,
        }

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
            query=term,
            base_url=self.config.base_url,
            max_results=max_results,
        )
