"""Transient-error retry helper for live HTTP sources.

Upstream genealogy sites (geneteka, genbaza, lubgens, ...) intermittently
return 5xx responses or briefly drop the connection. Surfacing those as
tool failures is unhelpful — a short exponential backoff almost always
recovers. The helper here wraps a single request callable, retries on
transient failures, and re-raises the last error if every attempt fails.

Tunable via environment:

* ``GENEALOGY_RETRY_MAX_ATTEMPTS`` — total attempts including the first
  (default 3).
* ``GENEALOGY_RETRY_BASE_DELAY`` — base delay in seconds; doubles each
  attempt (default 1.0).
* ``GENEALOGY_RETRY_MAX_DELAY`` — cap on a single backoff (default 30.0).
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Callable

import httpx

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504})

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    retry_statuses: frozenset[int] = RETRYABLE_STATUS_CODES,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Call ``send`` and retry on transient HTTP errors.

    Transient = an ``httpx`` transport/timeout error or a response whose
    status is in ``retry_statuses``. Non-transient responses are returned
    as-is (the caller is still responsible for ``raise_for_status``).
    """
    attempts = (
        max_attempts
        if max_attempts is not None
        else _env_int("GENEALOGY_RETRY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    )
    base = (
        base_delay
        if base_delay is not None
        else _env_float("GENEALOGY_RETRY_BASE_DELAY", DEFAULT_BASE_DELAY)
    )
    cap = (
        max_delay
        if max_delay is not None
        else _env_float("GENEALOGY_RETRY_MAX_DELAY", DEFAULT_MAX_DELAY)
    )
    attempts = max(1, attempts)

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        status: int | None = None
        try:
            resp = send()
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
        else:
            status = resp.status_code
            if status not in retry_statuses:
                return resp
            last_exc = httpx.HTTPStatusError(
                f"Upstream returned {status}",
                request=resp.request,
                response=resp,
            )

        if attempt >= attempts:
            break

        delay = min(cap, base * (2 ** (attempt - 1)))
        # Full jitter — keeps concurrent retries from re-colliding.
        delay = random.uniform(0, delay) if delay > 0 else 0.0
        LOGGER.warning(
            "Transient upstream error (status=%s, attempt=%d/%d); retrying in %.2fs",
            status,
            attempt,
            attempts,
            delay,
        )
        sleep(delay)

    assert last_exc is not None
    raise last_exc
