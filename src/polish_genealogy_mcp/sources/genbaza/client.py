"""Synchronous httpx client for the genbaza-family index sites."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

import httpx

from polish_genealogy_mcp.sources._http_retry import request_with_retry
from polish_genealogy_mcp.sources.genbaza.constants import (
    DEFAULT_COOKIES,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    ENDPOINT_PATH,
    PL2UNI,
    RECORD_TYPE_TO_RODZ,
    SITES,
)
from polish_genealogy_mcp.sources.genbaza.models import RecordType
from polish_genealogy_mcp.sources.genbaza.parser import (
    parse_resources_response,
    parse_search_response,
)


@dataclass
class GenbazaConfig:
    sites: dict[str, str] = field(default_factory=lambda: dict(SITES))
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GenbazaConfig":
        interval_env = os.environ.get("GENBAZA_MIN_INTERVAL")
        ua_env = os.environ.get("GENBAZA_USER_AGENT")
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


def pl2uni(text: str) -> str:
    """Replace Polish diacritics with the ``xNNN`` tokens the server expects."""
    for ch, token in PL2UNI.items():
        text = text.replace(ch, token)
    return text


class GenbazaClient:
    """Synchronous client. One instance per server is enough.

    Unlike the other sources in this repo, genbaza is multi-host: a single
    client serves five sibling subdomains. We don't pin httpx to a base
    URL; each request resolves the host through ``config.sites``.
    """

    def __init__(
        self,
        config: GenbazaConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or GenbazaConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=DEFAULT_COOKIES,
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GenbazaClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- public API ------------------------------------------------------

    def list_sites(self) -> dict[str, str]:
        return dict(self.config.sites)

    def search(
        self,
        site: str,
        *,
        record_type: RecordType = "birth",
        surname: str | None = None,
        given_name: str | None = None,
        father: str | None = None,
        mother: str | None = None,
        mother_surname: str | None = None,
        spouse: str | None = None,
        spouse_surname: str | None = None,
        place: str | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        other: str | None = None,
        parish_filter: str | None = None,
        page: int = 1,
        exact_surname: bool = False,
        exact_given_name: bool = False,
        exact_father: bool = False,
        exact_mother: bool = False,
        exact_mother_surname: bool = False,
        exact_spouse: bool = False,
        exact_spouse_surname: bool = False,
        exact_place: bool = False,
        exact_other: bool = False,
        method: int = 1,
        sort_by: int = 2,
    ):
        base = self._resolve(site)
        params = self._build_query(
            given=given_name,
            surname=surname,
            place=place,
            year_from=from_year,
            year_to=to_year,
            other=other,
            spouse=spouse,
            spouse_surname=spouse_surname,
            father=father,
            mother=mother,
            mother_surname=mother_surname,
            page=page,
            record_type=RECORD_TYPE_TO_RODZ[record_type],
            parish_filter=parish_filter,
            dokl=_encode_dokl(
                given=exact_given_name,
                surname=exact_surname,
                father=exact_father,
                mother=exact_mother,
                mother_surname=exact_mother_surname,
                spouse=exact_spouse,
                spouse_surname=exact_spouse_surname,
                place=exact_place,
                other=exact_other,
            ),
            method=method,
            sort1=sort_by,
            zasob=0,
        )
        body = self._get(base, params)
        result = parse_search_response(
            body, site=site, requested_record_type=RECORD_TYPE_TO_RODZ[record_type]
        )
        result.page = page
        return result

    def list_resources(self, site: str):
        base = self._resolve(site)
        params = self._build_query(
            given=None,
            surname=None,
            place=None,
            year_from=None,
            year_to=None,
            other=None,
            spouse=None,
            spouse_surname=None,
            father=None,
            mother=None,
            mother_surname=None,
            page=1,
            record_type=1,
            parish_filter=None,
            dokl=_encode_dokl(),
            method=1,
            sort1=0,
            zasob=1,
        )
        body = self._get(base, params)
        return parse_resources_response(body, site=site)

    # -- internals -------------------------------------------------------

    def _resolve(self, site: str) -> str:
        try:
            return self.config.sites[site]
        except KeyError as exc:
            known = ", ".join(sorted(self.config.sites))
            raise ValueError(f"Unknown genbaza site {site!r}. Known: {known}") from exc

    def _get(self, base: str, params: dict[str, str]) -> str:
        def _send() -> httpx.Response:
            self._limiter.wait()
            return self._client.get(
                f"{base}{ENDPOINT_PATH}",
                params=params,
                headers={"Referer": f"{base}/"},
            )

        resp = request_with_retry(_send)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _build_query(
        *,
        given: str | None,
        surname: str | None,
        place: str | None,
        year_from: int | None,
        year_to: int | None,
        other: str | None,
        spouse: str | None,
        spouse_surname: str | None,
        father: str | None,
        mother: str | None,
        mother_surname: str | None,
        page: int,
        record_type: int,
        parish_filter: str | None,
        dokl: str,
        method: int,
        sort1: int,
        zasob: int,
    ) -> dict[str, str]:
        # Order matches what the upstream JS sends. Polish chars get
        # pre-encoded to the xNNN tokens just like pl2uni() does in the
        # browser. Variant-B sites silently ignore the unused fields.
        raw = {
            "im": given or "",
            "naz": surname or "",
            "miejsc": place or "",
            "rok1": "" if year_from is None else str(year_from),
            "rok2": "" if year_to is None else str(year_to),
            "inne": other or "",
            "malz": spouse or "",
            "naz_malz": spouse_surname or "",
            "ojc": father or "",
            "mat": mother or "",
            "naz_mat": mother_surname or "",
            "pag": str(page),
            "sort1": str(sort1),
            "sort2": "1",
            "sort3": "0",
            "metr": parish_filter or "",
            "dokl": dokl,
            "metod": str(method),
            "rodz": str(record_type),
            "zasob": str(zasob),
        }
        return {k: pl2uni(v) for k, v in raw.items()}


def _encode_dokl(
    *,
    given: bool = False,
    surname: bool = False,
    father: bool = False,
    mother: bool = False,
    mother_surname: bool = False,
    spouse: bool = False,
    spouse_surname: bool = False,
    place: bool = False,
    other: bool = False,
) -> str:
    """Twelve-position bitmask of "exact match" toggles, in upstream
    order. Variant-B sites use the first 10 positions; the trailing two
    are silently ignored there. The last three positions are checkboxes
    that change the result sort order — we don't expose them as tools."""
    return "".join(
        "1" if v else "0"
        for v in (
            given,
            surname,
            father,
            mother,
            mother_surname,
            spouse,
            spouse_surname,
            place,
            other,
            False,
            False,
            False,
        )
    )
