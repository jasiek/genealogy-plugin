"""Unit tests for the shared transient-error retry helper."""

from __future__ import annotations

import httpx
import pytest

from polish_genealogy_mcp.sources._http_retry import request_with_retry


def _ok() -> httpx.Response:
    return httpx.Response(200, text="ok", request=httpx.Request("GET", "https://x/"))


def _status(code: int) -> httpx.Response:
    return httpx.Response(code, text=str(code), request=httpx.Request("GET", "https://x/"))


def test_returns_immediately_on_success():
    calls = {"n": 0}

    def send() -> httpx.Response:
        calls["n"] += 1
        return _ok()

    resp = request_with_retry(send, sleep=lambda _s: None)
    assert resp.status_code == 200
    assert calls["n"] == 1


def test_retries_on_502_then_succeeds():
    responses = [_status(502), _status(502), _ok()]

    def send() -> httpx.Response:
        return responses.pop(0)

    sleeps: list[float] = []
    resp = request_with_retry(
        send,
        max_attempts=3,
        base_delay=1.0,
        sleep=sleeps.append,
    )
    assert resp.status_code == 200
    assert len(sleeps) == 2  # two backoffs between three attempts


def test_retries_on_transport_error_then_succeeds():
    calls = {"n": 0}

    def send() -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom")
        return _ok()

    resp = request_with_retry(send, max_attempts=3, base_delay=0, sleep=lambda _s: None)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_raises_after_exhausting_attempts_on_5xx():
    def send() -> httpx.Response:
        return _status(503)

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(send, max_attempts=3, base_delay=0, sleep=lambda _s: None)


def test_raises_after_exhausting_attempts_on_transport_error():
    def send() -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(httpx.ReadTimeout):
        request_with_retry(send, max_attempts=2, base_delay=0, sleep=lambda _s: None)


def test_does_not_retry_non_retryable_status():
    calls = {"n": 0}

    def send() -> httpx.Response:
        calls["n"] += 1
        return _status(404)

    resp = request_with_retry(send, max_attempts=5, base_delay=0, sleep=lambda _s: None)
    assert resp.status_code == 404
    assert calls["n"] == 1


def test_backoff_is_bounded_by_max_delay():
    responses = [_status(502)] * 5 + [_ok()]

    def send() -> httpx.Response:
        return responses.pop(0)

    sleeps: list[float] = []
    request_with_retry(
        send,
        max_attempts=6,
        base_delay=10.0,
        max_delay=2.0,
        sleep=sleeps.append,
    )
    # Full-jitter samples in [0, capped_delay]; capped_delay never exceeds max_delay.
    assert all(0 <= s <= 2.0 for s in sleeps)
