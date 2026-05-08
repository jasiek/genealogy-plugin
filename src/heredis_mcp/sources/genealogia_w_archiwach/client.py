"""Thin UIDL client for Genealogia w Archiwach's Vaadin application."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from heredis_mcp.sources.genealogia_w_archiwach.constants import (
    ACT_TYPE_KEYS,
    APP_PATH,
    BASE_URL,
    DEFAULT_MIN_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    PERSON_ROLE_KEYS,
    SEARCH_SCOPE_KEYS,
    UIDL_PATH,
)
from heredis_mcp.sources.genealogia_w_archiwach.models import (
    ActType,
    PersonRole,
    SearchScope,
)
from heredis_mcp.sources.genealogia_w_archiwach.parser import (
    parse_bootstrap_uidl,
    parse_uidl_text,
)


@dataclass
class GenealogiaWArchiwachConfig:
    base_url: str = BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GenealogiaWArchiwachConfig":
        interval_env = os.environ.get("GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL")
        ua_env = os.environ.get("GENEALOGIA_W_ARCHIWACH_USER_AGENT")
        base_url = os.environ.get("GENEALOGIA_W_ARCHIWACH_BASE_URL")
        return cls(
            base_url=base_url or BASE_URL,
            min_interval_seconds=(
                float(interval_env) if interval_env else DEFAULT_MIN_INTERVAL_SECONDS
            ),
            user_agent=ua_env or DEFAULT_USER_AGENT,
        )


@dataclass
class VaadinSession:
    csrf_token: str
    sync_id: int
    client_id: int
    ui_id: int
    intro_closed: bool = False


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


class GenealogiaWArchiwachClient:
    """Synchronous client for the site's Vaadin UIDL protocol."""

    def __init__(self, config: GenealogiaWArchiwachConfig | None = None) -> None:
        self.config = config or GenealogiaWArchiwachConfig.from_env()
        self._limiter = _RateLimiter(self.config.min_interval_seconds)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={"User-Agent": self.config.user_agent},
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
        )
        self._session: VaadinSession | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GenealogiaWArchiwachClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def search_person(
        self,
        *,
        query: str | None = None,
        given_name: str | None = None,
        surname: str | None = None,
        act_type: ActType | None = None,
        role: PersonRole | None = None,
        scope: SearchScope = "all",
        from_year: int | None = None,
        to_year: int | None = None,
        place: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the Vaadin app and return raw UIDL messages.

        The site does not expose a stable documented search API. These RPCs
        mirror the current public Vaadin form component ids and are isolated
        here so future site changes do not leak into MCP tool code.
        """
        session = self._ensure_session()
        self._close_intro_overlay(session)

        if query:
            self._set_text_field(session, "17", query)
        if surname:
            self._set_text_field(session, "23", surname)
        if given_name:
            self._set_text_field(session, "26", given_name)

        rpc: list[list[Any]] = []
        # ComboBox value updates in this Vaadin app are legacy variable
        # changes. Keep them separate from text fields so the default query
        # path remains identical to the captured browser flow.
        if place:
            rpc.append(_legacy_var("19", "filter", "s", place))
        if role:
            rpc.append(_legacy_var("20", "selected", "s", PERSON_ROLE_KEYS[role]))
        if act_type:
            rpc.append(_legacy_var("21", "selected", "s", ACT_TYPE_KEYS[act_type]))
        if to_year is not None:
            rpc.append(_legacy_var("22", "filter", "s", str(to_year)))
        if from_year is not None:
            rpc.append(_legacy_var("24", "filter", "s", str(from_year)))
        if scope != "all":
            rpc.append(_legacy_var("18", "selected", "s", SEARCH_SCOPE_KEYS[scope]))

        rpc.append(["27", "com.vaadin.shared.ui.button.ButtonServerRpc", "click", [_click_event()]])

        return self._post_uidl(session, rpc)

    def _ensure_session(self) -> VaadinSession:
        if self._session is not None:
            return self._session

        self._limiter.wait()
        self._client.get(f"{APP_PATH}?locale=pl#")

        params = self._browser_details_params()
        self._limiter.wait()
        resp = self._client.post(
            f"{APP_PATH}?locale=pl&v-{int(time.time() * 1000)}",
            content=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        uidl = parse_bootstrap_uidl(resp.text)
        self._session = VaadinSession(
            csrf_token=str(uidl["Vaadin-Security-Key"]),
            sync_id=int(uidl.get("syncId", 0)),
            client_id=int(uidl.get("clientId", 0)),
            ui_id=int(uidl.get("v-uiId", 0)),
        )
        return self._session

    def _close_intro_overlay(self, session: VaadinSession) -> None:
        if session.intro_closed:
            return
        rpc = [
            _legacy_var("29", "positionx", "i", 0),
            _legacy_var("29", "positiony", "i", 0),
            ["0", "com.vaadin.shared.ui.ui.UIServerRpc", "resize", [900, 1280, 1280, 900]],
            [
                "34",
                "com.vaadin.shared.ui.button.ButtonServerRpc",
                "click",
                [_click_event(640, 82, 308, 21)],
            ],
        ]
        self._post_uidl(session, rpc, extra={"wsver": "7.7.17"})
        session.intro_closed = True

    def _set_text_field(self, session: VaadinSession, pid: str, value: str) -> None:
        self._post_uidl(session, [_legacy_var(pid, "focus", "s", "")])
        self._post_uidl(
            session,
            [
                _legacy_var(pid, "text", "s", value),
                _legacy_var(pid, "c", "i", len(value)),
                _legacy_var(pid, "blur", "s", ""),
            ],
        )

    def _post_uidl(
        self,
        session: VaadinSession,
        rpc: list[list[Any]],
        *,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = {
            "csrfToken": session.csrf_token,
            "rpc": rpc,
            "syncId": session.sync_id,
            "clientId": session.client_id,
        }
        if extra:
            payload.update(extra)
        self._limiter.wait()
        resp = self._client.post(
            f"{UIDL_PATH}?v-uiId={session.ui_id}",
            json=payload,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        messages = parse_uidl_text(resp.text)
        if messages:
            last = messages[-1]
            session.sync_id = int(last.get("syncId", session.sync_id))
            session.client_id = int(last.get("clientId", session.client_id))
        return messages

    def _browser_details_params(self) -> str:
        loc = f"{self.config.base_url.rstrip('/')}{APP_PATH}?locale=pl#"
        return (
            "v-browserDetails=1&theme=mytheme&v-appId=ROOT-2521314"
            "&v-sh=900&v-sw=1440&v-cw=1280&v-ch=720"
            f"&v-curdate={int(time.time() * 1000)}"
            "&v-tzo=-120&v-dstd=60&v-rtzo=-60&v-dston=true"
            "&v-vw=1280&v-vh=720"
            f"&v-loc={quote(loc, safe='')}"
            "&v-wn=ROOT-2521314-mcp"
        )


def _legacy_var(pid: str, name: str, type_code: str, value: object) -> list[Any]:
    return [pid, "v", "v", [name, [type_code, value]]]


def _click_event(
    client_x: int = 1045,
    client_y: int = 79,
    relative_x: int = 101,
    relative_y: int = 18,
) -> dict[str, object]:
    return {
        "button": "LEFT",
        "clientX": client_x,
        "clientY": client_y,
        "relativeX": relative_x,
        "relativeY": relative_y,
        "altKey": False,
        "ctrlKey": False,
        "metaKey": False,
        "shiftKey": False,
        "type": 1,
    }
