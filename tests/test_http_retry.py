"""Unit tests for the RetryTransport middleware."""

from __future__ import annotations

import httpx
import pytest

from polish_genealogy_mcp.sources._http_retry import RetryTransport


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip backoff sleeps so the suite stays fast."""
    monkeypatch.setattr("polish_genealogy_mcp.sources._http_retry.time.sleep", lambda _s: None)


def _client(handler) -> httpx.Client:
    inner = httpx.MockTransport(handler)
    return httpx.Client(transport=RetryTransport(inner))


def test_returns_immediately_on_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="ok")

    with _client(handler) as client:
        resp = client.get("https://x/")

    assert resp.status_code == 200
    assert calls["n"] == 1


def test_retries_5xx_then_succeeds():
    statuses = iter([502, 502, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), text="hi")

    with _client(handler) as client:
        resp = client.get("https://x/")

    assert resp.status_code == 200
    assert resp.text == "hi"


def test_returns_last_5xx_after_exhausting_attempts():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="oops")

    inner = httpx.MockTransport(handler)
    with httpx.Client(transport=RetryTransport(inner, max_attempts=3)) as client:
        resp = client.get("https://x/")

    assert resp.status_code == 503
    assert resp.text == "oops"  # body still readable after wrap+close
    assert calls["n"] == 3


def test_retries_transport_errors_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom")
        return httpx.Response(200)

    with _client(handler) as client:
        resp = client.get("https://x/")

    assert resp.status_code == 200
    assert calls["n"] == 2


def test_raises_after_exhausting_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    inner = httpx.MockTransport(handler)
    with httpx.Client(transport=RetryTransport(inner, max_attempts=2)) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.get("https://x/")


def test_does_not_retry_non_retryable_status():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with _client(handler) as client:
        resp = client.get("https://x/")

    assert resp.status_code == 404
    assert calls["n"] == 1


def test_close_propagates_to_wrapped_transport():
    closed = {"flag": False}

    class _Probe(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200)

        def close(self) -> None:
            closed["flag"] = True

    transport = RetryTransport(_Probe())
    transport.close()
    assert closed["flag"] is True
