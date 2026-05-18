"""Parsers for Vaadin UIDL responses from Genealogia w Archiwach."""

from __future__ import annotations

import json
import re
from html import unescape
from collections.abc import Iterable
from typing import Any

from genealogy_mcp.sources.genealogia_w_archiwach.constants import BASE_URL
from genealogy_mcp.sources.genealogia_w_archiwach.models import (
    GenealogiaWArchiwachRecord,
)

VAADIN_JSON_PREFIX = "for(;;);"
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+|(?<!<)/(?:[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+)")
IMAGE_HINT_RE = re.compile(
    r"(\.(?:jpe?g|png|webp)(?:[?#].*)?$|/iiif/|/image/|/images?/|/tiles?/|/info\.json$)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
HTML_TAG_RE = re.compile(r"<[^>]+>")
FIELD_RE = re.compile(
    r'class="fat">(?P<key>.*?)</div>\s*<div class="fat-value">\s*(?P<value>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
IGNORED_DESCRIPTIONS = {
    "Pokaż skan",
    "Liczba indeksów",
    "Informacje o zespole archiwalnym",
}


def parse_uidl_text(text: str) -> list[dict[str, Any]]:
    """Parse a Vaadin UIDL response into its top-level message objects."""
    payload = text.strip()
    if payload.startswith(VAADIN_JSON_PREFIX):
        payload = payload[len(VAADIN_JSON_PREFIX) :]
    data = json.loads(payload)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def parse_bootstrap_uidl(text: str) -> dict[str, Any]:
    """Parse the JSON returned by Vaadin's browser-details bootstrap POST."""
    outer = json.loads(text)
    uidl = outer.get("uidl")
    if isinstance(uidl, str):
        return json.loads(uidl)
    if isinstance(uidl, dict):
        return uidl
    return outer


def extract_urls(payload: Any, *, base_url: str = BASE_URL) -> list[str]:
    """Extract absolute and site-relative URLs from nested UIDL JSON."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if "fonticon://" in value:
            return
        for match in URL_RE.findall(value):
            url = match.rstrip(".,);]")
            if url.startswith("//FontAwesome") or "/FontAwesome/" in url:
                continue
            if url.startswith("/"):
                url = base_url.rstrip("/") + url
            if url not in seen:
                seen.add(url)
                urls.append(url)

    for text in _walk_strings(payload):
        add(text)
    return urls


def image_urls(urls: Iterable[str]) -> list[str]:
    """Return URLs that look like scan, image, IIIF, or tile resources."""
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if IMAGE_HINT_RE.search(url) and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def parse_records(
    messages: list[dict[str, Any]], *, base_url: str = BASE_URL
) -> list[GenealogiaWArchiwachRecord]:
    """Extract candidate result cards from UIDL messages.

    The upstream app renders several custom result components. Their stable
    public contract is weak, so this parser favors user-visible text and URLs
    over internal widget details.
    """
    records: list[GenealogiaWArchiwachRecord] = []
    for message in messages:
        type_names = _type_name_by_id(message)
        hierarchy = message.get("hierarchy") or {}
        changes = _changes_by_pid(message)
        state = _state_by_pid(message)
        result_pids = [
            pid
            for pid, change in changes.items()
            if _is_result_type(type_names.get(_change_type(change), ""))
        ]
        for pid in result_pids:
            subtree = _collect_subtree(pid, hierarchy, changes, state)
            strings = list(_walk_strings(subtree))
            raw_text = _visible_text(strings)
            urls = extract_urls(subtree, base_url=base_url)
            imgs = image_urls(urls)
            fields = _fields_from_strings(strings)
            description = (
                _document_name_description(pid, hierarchy, state)
                or _first_description(subtree)
                or (raw_text[:500] if raw_text else None)
            )
            year = _first_year(fields.get("data")) or _first_year(raw_text)
            identifiers = {"pid": pid}
            for field_name in ("jednostka archiwalna", "sygnatura", "strona", "zespół"):
                if fields.get(field_name):
                    identifiers[field_name] = fields[field_name]
            records.append(
                GenealogiaWArchiwachRecord(
                    title=description,
                    description=description,
                    year=year,
                    place=fields.get("miejscowość"),
                    source_url=_first_non_image_url(urls),
                    image_urls=imgs,
                    urls=urls,
                    identifiers=identifiers,
                    raw_text=raw_text or None,
                )
            )
    return records


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _type_name_by_id(message: dict[str, Any]) -> dict[str, str]:
    mappings = message.get("typeMappings") or {}
    return {str(type_id): name for name, type_id in mappings.items()}


def _changes_by_pid(message: dict[str, Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for change in message.get("changes") or []:
        if (
            isinstance(change, list)
            and len(change) >= 3
            and change[0] == "change"
            and isinstance(change[1], dict)
        ):
            pid = change[1].get("pid")
            if pid is not None:
                out[str(pid)] = change
    return out


def _state_by_pid(message: dict[str, Any]) -> dict[str, Any]:
    state = message.get("state") or {}
    if not isinstance(state, dict):
        return {}
    return {str(pid): value for pid, value in state.items()}


def _change_type(change: list[Any]) -> str:
    try:
        return str(change[2][0])
    except (IndexError, TypeError):
        return ""


def _is_result_type(type_name: str) -> bool:
    if not type_name.endswith("SearchResult"):
        return False
    return not type_name.endswith("SearchResultDetails")


def _collect_subtree(
    pid: str,
    hierarchy: dict[str, list[str]],
    changes: dict[str, list[Any]],
    state: dict[str, Any],
) -> list[Any]:
    out: list[Any] = []
    stack = [pid]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in changes:
            out.append(changes[current])
        if current in state:
            out.append(state[current])
        stack.extend(reversed([str(child) for child in hierarchy.get(current, [])]))
    return out


def _first_description(value: Any) -> str | None:
    if isinstance(value, dict):
        description = value.get("description")
        clean_description = _clean_visible_text(description) if isinstance(description, str) else ""
        if clean_description and clean_description not in IGNORED_DESCRIPTIONS:
            return clean_description
        for child in value.values():
            found = _first_description(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_description(child)
            if found:
                return found
    return None


def _document_name_description(
    pid: str, hierarchy: dict[str, list[str]], state: dict[str, Any]
) -> str | None:
    result_state = state.get(pid)
    if not isinstance(result_state, dict):
        return None
    child_locations = result_state.get("childLocations")
    if not isinstance(child_locations, dict):
        return None
    document_name_pid = next(
        (
            str(child_pid)
            for child_pid, location in child_locations.items()
            if location == "document_name"
        ),
        None,
    )
    if not document_name_pid:
        return None
    subtree = _collect_subtree(document_name_pid, hierarchy, {}, state)
    return _first_description(subtree)


def _fields_from_strings(strings: Iterable[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for text in strings:
        if "fat-value" not in text:
            continue
        for match in FIELD_RE.finditer(text):
            key = _clean_visible_text(match.group("key")).lower()
            value = _clean_visible_text(match.group("value"))
            if key and value and key not in fields:
                fields[key] = value
    return fields


def _visible_text(strings: Iterable[str]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for text in strings:
        clean = _clean_visible_text(text)
        if not clean or clean in seen:
            continue
        if clean.startswith(("pl.bos.", "com.vaadin.", "v-", "fonticon://")):
            continue
        seen.add(clean)
        parts.append(clean)
    return " ".join(parts)


def _clean_visible_text(value: str) -> str:
    return _clean_text(unescape(HTML_TAG_RE.sub(" ", value)))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_year(text: str | None) -> int | None:
    if not text:
        return None
    match = YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def _first_non_image_url(urls: list[str]) -> str | None:
    for url in urls:
        if not IMAGE_HINT_RE.search(url):
            return url
    return urls[0] if urls else None
