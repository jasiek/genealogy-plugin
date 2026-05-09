"""Transient-error retry middleware for httpx clients.

Upstream genealogy sites (Geneteka, GenBaza, Lubgens, ...) intermittently
return 5xx responses or briefly drop the connection. ``RetryTransport``
wraps another ``httpx.BaseTransport`` and re-issues each request with
full-jitter exponential backoff on:

* ``httpx.TransportError`` / ``httpx.TimeoutException``
* HTTP 502 / 503 / 504

Use it once at client construction; retry then becomes invisible to call
sites:

    client = httpx.Client(transport=RetryTransport(), ...)

If retries are exhausted on a 5xx, the last response is returned as-is
(the caller's ``raise_for_status`` keeps its old behaviour). If retries
are exhausted on a transport error, the last exception is re-raised.
"""

from __future__ import annotations

import logging
import random
import time

import httpx

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504})

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0


class RetryTransport(httpx.BaseTransport):
    """An ``httpx`` transport that retries on transient errors."""

    def __init__(
        self,
        wrapped: httpx.BaseTransport | None = None,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        base_delay: float = BASE_DELAY_SECONDS,
        max_delay: float = MAX_DELAY_SECONDS,
        retry_statuses: frozenset[int] = RETRYABLE_STATUS_CODES,
    ) -> None:
        self._wrapped = wrapped if wrapped is not None else httpx.HTTPTransport()
        self._max_attempts = max(1, max_attempts)
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retry_statuses = retry_statuses

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: BaseException | None = None
        last_resp: httpx.Response | None = None

        for attempt in range(1, self._max_attempts + 1):
            status: int | None = None
            try:
                resp = self._wrapped.handle_request(request)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc, last_resp = exc, None
            else:
                status = resp.status_code
                if status not in self._retry_statuses:
                    return resp
                # Buffer the body so the caller can still read .text/.json
                # after we've released the underlying connection.
                resp.read()
                resp.close()
                last_exc, last_resp = None, resp

            if attempt >= self._max_attempts:
                break

            delay = min(self._max_delay, self._base_delay * (2 ** (attempt - 1)))
            # Full jitter: keeps concurrent retries from re-colliding.
            delay = random.uniform(0, delay) if delay > 0 else 0.0
            LOGGER.warning(
                "Transient upstream error (status=%s, attempt=%d/%d); retrying in %.2fs",
                status,
                attempt,
                self._max_attempts,
                delay,
            )
            time.sleep(delay)

        if last_resp is not None:
            return last_resp
        assert last_exc is not None
        raise last_exc

    def close(self) -> None:
        self._wrapped.close()
