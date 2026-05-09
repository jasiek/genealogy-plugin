"""Transient-error retry helper for live HTTP sources.

Upstream genealogy sites (geneteka, genbaza, lubgens, ...) intermittently
return 5xx responses or briefly drop the connection. Surfacing those as
tool failures is unhelpful — a short exponential backoff almost always
recovers. The helper here wraps a single request callable, retries on
transient failures, and re-raises the last error if every attempt fails.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable

import httpx

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504})

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    base_delay: float = BASE_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    retry_statuses: frozenset[int] = RETRYABLE_STATUS_CODES,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Call ``send`` and retry on transient HTTP errors.

    Transient = an ``httpx`` transport/timeout error or a response whose
    status is in ``retry_statuses``. Non-transient responses are returned
    as-is (the caller is still responsible for ``raise_for_status``).
    """
    attempts = max(1, max_attempts)

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

        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
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
